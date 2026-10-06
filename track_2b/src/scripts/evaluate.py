import argparse
import hashlib
import json
import os
import random
import re
import statistics
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from app.config import settings
from app.models import Athlete, Course
from app.services import llm
from app.services.analyzer import ANALYZE_SYSTEM, run_analysis
from app.services.llm import LLMError
from app.services.parser import PARSE_SYSTEM, parse_workout_text
from app.services.planner import PLAN_SYSTEM, build_plan
from scripts.seed import PROFILES

EVAL_DIR = Path(
    os.environ.get("EVAL_DIR", Path(__file__).resolve().parents[2] / "data" / "eval")
)


class CallLog:
    """
    Подменяет llm._complete: считает вызовы, время и сохраняет каждый сырой ответ.
    Два вызова на один кейс значат, что первый ответ не прошёл проверку и был повтор.

    Шлюз Public AI кэширует одинаковые запросы: повтор того же кейса приходил за 0.4 с
    и был копией первого ответа. Поэтому к системному сообщению добавляем метку прогона,
    и каждый повтор становится новым запросом. В приложении метки нет.
    """

    def __init__(self, run_id: str):
        self.original = llm._complete
        self.run_id = run_id
        self.reset("")

    def reset(self, tag: str):
        self.tag = tag
        self.calls, self.seconds, self.responses = 0, 0.0, []

    def __call__(self, messages, temperature):
        messages = [dict(m) for m in messages]  # копия: не трогаем список chat_json
        messages[0]["content"] += f"\n\n[evaluation run {self.run_id}, case {self.tag}]"
        started = time.perf_counter()
        try:
            answer = self.original(messages, temperature)
        finally:
            self.calls += 1
            self.seconds += time.perf_counter() - started
        self.responses.append(answer)
        return answer


def run_case(log: CallLog, tag: str, fn):
    """Запускает fn, ловит LLMError и возвращает (результат или None, ошибка, статистика вызовов)."""
    log.reset(tag)
    try:
        result, error = fn(), None
    except LLMError as e:
        result, error = None, str(e)[:300]
    stats = {
        "calls": log.calls,
        "seconds": round(log.seconds, 2),
        "raw_responses": list(log.responses),
    }
    return result, error, stats


# ---------- parse ----------


def _set_key(s: dict, timing: bool) -> tuple:
    key = (s["stroke"], s["distance"], s.get("reps") or 1)
    return key + (s.get("interval_s"), s.get("rest_s")) if timing else key


def score_parse(expected: dict, got: dict) -> dict:
    """Поле за полем: совпало ли с правильным ответом."""
    exp_sets, got_sets = expected["sets"], got["sets"]
    symptoms = " ".join(got["symptoms"]).lower()
    want = expected["symptoms"]
    return {
        "course": got["course"] == expected["course"],
        "duration": got["duration_min"] == expected["duration_min"],
        "effort": got["perceived_effort"] == expected["perceived_effort"],
        # состав серий: стиль, дистанция, повторы (порядок не важен)
        "sets": Counter(_set_key(s, False) for s in got_sets)
        == Counter(_set_key(s, False) for s in exp_sets),
        # то же плюс режим и отдых
        "intervals": Counter(_set_key(s, True) for s in got_sets)
        == Counter(_set_key(s, True) for s in exp_sets),
        "total": got["total_distance"] == expected["total_distance"],
        # нужные симптомы найдены и на английском; если симптомов нет, список пустой
        "symptoms": (
            all(re.search(p, symptoms) for p in want) and symptoms.isascii()
            if want
            else not got["symptoms"]
        ),
    }


def eval_parse(log: CallLog, cases: list[dict], repeats: int) -> list[dict]:
    rows = []
    for case in cases:
        for rep in range(repeats):
            parsed, error, stats = run_case(
                log, f"{case['id']}#{rep}", lambda: parse_workout_text(case["text"])
            )
            got = parsed.model_dump(mode="json") if parsed else None
            rows.append(
                {
                    "task": "parse",
                    "case_id": case["id"],
                    "language": case["language"],
                    "split": case.get("split", "dev"),
                    "repeat": rep,
                    "ok": parsed is not None,
                    "error": error,
                    **stats,
                    "output": got,
                    "score": score_parse(case["expected"], got) if got else None,
                }
            )
            print(
                f"  parse {case['id']} #{rep}: {'ok' if got else 'FAILED'} "
                f"{'' if not got else sum(rows[-1]['score'].values())}/7 fields, {stats['calls']} call(s)"
            )
    return rows


# ---------- analysis и plan на демо-профилях ----------


def build_profile(name: str, today: date) -> tuple[Athlete, list]:
    """Тот же спортсмен, что создаёт seed.py, только в памяти, без базы."""
    for profile_name, strokes, goal, weeks_out, make, seed in PROFILES:
        if profile_name.lower() == name:
            athlete = Athlete(
                name=f"Demo: {profile_name}",
                main_strokes=strokes,
                goal_event=goal,
                goal_date=today + timedelta(weeks=weeks_out),
            )
            return athlete, make(random.Random(seed), today)
    raise ValueError(f"unknown profile {name}")


def score_analysis(case: dict, analysis: dict, warnings: list[str]) -> dict:
    types = {c["type"] for c in analysis["concerns"]}
    return {
        "expected_found": all(t in types for t in case["expected_concerns"]),
        "nothing_forbidden": not any(t in types for t in case["forbidden_concerns"]),
        "grounded": not warnings,
    }


def score_plan(case: dict, plan: dict, goal_stroke: str) -> dict:
    sets = " ".join((d.get("main_set") or "").lower() for d in plan["days"])
    score = {
        # попала ли модель в объём сама, до масштабирования кодом
        "model_within_target": plan["model_within_target"],
        "final_within_target": (
            plan["volume_target_m"]["min"]
            <= plan["total_distance_m"]
            <= plan["volume_target_m"]["max"]
            if plan["volume_target_m"]
            else None
        ),
        # правила после повтора: тяжёлые дни, длина серий, предупреждения
        "rules_ok": not plan["rule_warnings"],
        "grounded": not plan["grounding_warnings"],
    }
    if "symptom" in case["expected_concerns"]:
        score["cautions_present"] = bool(plan.get("cautions"))
        # нагрузку на стиль снижаем, но не убираем его из недели
        score["goal_stroke_kept"] = (
            goal_stroke in sets or {"fly": "butterfly"}.get(goal_stroke, "") in sets
        )
    return score


def eval_profiles(
    log: CallLog, cases: list[dict], repeats: int, tasks: set[str]
) -> list[dict]:
    today = date.today()
    rows = []
    for case in cases:
        athlete, history = build_profile(case["profile"], today)
        goal_stroke = athlete.goal_event.split()[-1]  # "100 fly" -> "fly"
        for rep in range(repeats):
            analysis_dict = None
            if "analysis" in tasks:
                result, error, stats = run_case(
                    log,
                    f"{case['id']}#{rep}",
                    lambda: run_analysis(athlete, history, today),
                )
                if result:
                    analysis, _raw, warnings = result
                    analysis_dict = {
                        **analysis.model_dump(),
                        "grounding_warnings": warnings,
                    }
                rows.append(
                    {
                        "task": "analysis",
                        "case_id": case["id"],
                        "profile": case["profile"],
                        "repeat": rep,
                        "ok": result is not None,
                        "error": error,
                        **stats,
                        "output": analysis_dict,
                        "score": (
                            score_analysis(
                                case, analysis_dict, analysis_dict["grounding_warnings"]
                            )
                            if analysis_dict
                            else None
                        ),
                    }
                )
                print(
                    f"  analysis {case['profile']} #{rep}: "
                    f"{rows[-1]['score'] if result else 'FAILED'}, {stats['calls']} call(s)"
                )
            if "plan" in tasks:
                # как в приложении: план видит последний анализ этого же прогона
                result, error, stats = run_case(
                    log,
                    f"{case['id']}-plan#{rep}",
                    lambda: build_plan(athlete, history, analysis_dict, today),
                )
                plan = result[0] if result else None
                rows.append(
                    {
                        "task": "plan",
                        "case_id": case["id"],
                        "profile": case["profile"],
                        "repeat": rep,
                        "ok": plan is not None,
                        "error": error,
                        **stats,
                        "output": plan,
                        "score": score_plan(case, plan, goal_stroke) if plan else None,
                    }
                )
                print(
                    f"  plan {case['profile']} #{rep}: "
                    f"{rows[-1]['score'] if plan else 'FAILED'}, {stats['calls']} call(s)"
                )
    return rows


# ---------- сводка ----------


def pct(values: list) -> str:
    values = [v for v in values if v is not None]
    return f"{100 * sum(values) / len(values):.0f}%" if values else "n/a"


# Метрики самой модели, а не системы: их показываем, но в «решено целиком» не включаем.
# model_within_target: попала ли модель в объём сама; итог всё равно доводит код.
DIAGNOSTIC = {"model_within_target"}


def correct(row: dict) -> bool:
    """Случай решён целиком. Упавший запуск (модель не дала валидный ответ) считается ошибкой."""
    return row["ok"] and all(
        v for k, v in row["score"].items() if v is not None and k not in DIAGNOSTIC
    )


def summarize_rows(rows: list[dict]) -> dict:
    summary = {}
    for task in ("parse", "analysis", "plan"):
        task_rows = [r for r in rows if r["task"] == task]
        if not task_rows:
            continue
        ok = [r for r in task_rows if r["ok"]]
        metrics = sorted({k for r in ok for k in r["score"]})
        summary[task] = {
            "runs": len(task_rows),
            "valid_output": pct([r["ok"] for r in task_rows]),
            "first_try": pct([r["ok"] and r["calls"] == 1 for r in task_rows]),
            "median_seconds": round(
                statistics.median(r["seconds"] for r in task_rows), 1
            ),
            # точность по отдельным полям считаем среди валидных ответов
            **{m: pct([r["score"].get(m) for r in ok]) for m in metrics},
            # а «решено целиком» — среди всех запусков, упавшие тоже в знаменателе
            "all_correct": pct([correct(r) for r in task_rows]),
        }
        groups = {"parse": ("split", "language")}.get(task, ("profile",))
        for key in groups:
            # dev: случаи, по которым правили промпт; holdout: написаны до правки, под них не подгоняли
            summary[task][f"by_{key}"] = {
                value: pct([correct(r) for r in task_rows if r[key] == value])
                for value in sorted({r[key] for r in task_rows})
            }
    return summary


def to_markdown(meta: dict, summary: dict) -> str:
    lines = [
        f"# Evaluation: {meta['model']}",
        "",
        f"{meta['started']}, {meta['repeats']} repeat(s), endpoint `{meta['base_url']}`",
        "prompts: " + ", ".join(f"{k} `{v}`" for k, v in meta["prompts"].items()),
        "",
    ]
    for task, values in summary.items():
        lines += [f"## {task}", "", "| metric | value |", "|---|---|"]
        for key, value in values.items():
            if isinstance(value, dict):
                value = ", ".join(f"{k}: {v}" for k, v in value.items())
            lines.append(f"| {key} | {value} |")
        lines.append("")
    return "\n".join(lines)


def load(name: str) -> list[dict]:
    with open(EVAL_DIR / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Alpenstroke against the configured model."
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="runs per case (the model is not deterministic)",
    )
    parser.add_argument(
        "--only",
        choices=["parse", "analysis", "plan"],
        action="append",
        help="run only these tasks; can be repeated",
    )
    args = parser.parse_args()
    tasks = set(args.only or ["parse", "analysis", "plan"])

    started = datetime.now()
    log = CallLog(run_id=f"{started:%Y%m%d-%H%M%S}")
    llm._complete = log  # chat_json зовёт llm._complete, поэтому подмена видна везде

    meta = {
        "model": settings.llm_name,
        "base_url": settings.llm_base_url,
        "started": started.isoformat(timespec="seconds"),
        "repeats": args.repeats,
        "tasks": sorted(tasks),
        # короткие отпечатки промптов: по ним видно, какой версией сделан прогон
        "prompts": {
            name: hashlib.sha256(text.encode()).hexdigest()[:8]
            for name, text in (
                ("parse", PARSE_SYSTEM),
                ("analysis", ANALYZE_SYSTEM),
                ("plan", PLAN_SYSTEM),
            )
        },
    }
    print(f"Evaluating {meta['model']} at {meta['base_url']}")

    rows = []
    if "parse" in tasks:
        rows += eval_parse(log, load("parse_cases.jsonl"), args.repeats)
    if tasks & {"analysis", "plan"}:
        rows += eval_profiles(log, load("profile_cases.jsonl"), args.repeats, tasks)

    summary = summarize_rows(rows)
    slug = re.sub(r"[^A-Za-z0-9.-]+", "-", settings.llm_name).strip("-")
    out = EVAL_DIR / "runs" / f"{started:%Y%m%d-%H%M%S}_{slug}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "responses.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(
                json.dumps(
                    {**row, "model": settings.llm_name}, ensure_ascii=False, default=str
                )
                + "\n"
            )
    (out / "summary.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, indent=2)
    )
    markdown = to_markdown(meta, summary)
    (out / "summary.md").write_text(markdown)

    print("\n" + markdown)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
