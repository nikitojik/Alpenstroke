import json
import math
import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import AIRecommendation, Athlete, Kind, Workout
from app.schemas.plan import WeeklyPlan
from app.services.analyzer import HISTORY_DAYS, _set_line
from app.services.grounding import (
    body_part_check,
    grounding_sources,
    ungrounded_body_parts,
)
from app.services.llm import chat_json
from app.services.metrics import summarize, to_meters

PLAN_SYSTEM = """You are an experienced swim coach. You write a 7-day training plan.

You receive JSON with:
- "plan_dates": the 7 dates to plan, in order, with weekdays.
- "athlete": main strokes, goal event, goal date and days until it.
- "metrics": training-load numbers computed by code. Trust them.
- "recent_workouts": the last sessions with sets and the swimmer's notes.
- "latest_analysis": the most recent coach analysis with concerns, or null.
- "volume_target_m": the weekly volume range computed by code, with the reason, or null.

Rules:
- Return exactly 7 days, one per date in plan_dates, in the same order.
- If volume_target_m is not null, the sum of distance_m over the 7 days MUST be between
  volume_target_m.min and volume_target_m.max.
- If volume_target_m is null, there is not enough history to set a target: base each session
  on the distances in recent_workouts.
- ONLY IF latest_analysis contains a concern of type "symptom": reduce the load on what triggers
  it instead of banning it (short repeats, drills, broken sets, fins or more rest instead of full
  sets). Keep the athlete's main stroke in the week if it is their goal event.
- If latest_analysis is null or has no "symptom" concern, cautions must not mention symptoms,
  discomfort or limiting any stroke. Use null for cautions if there is nothing to warn about.
- Never write that something was "noted" or "reported" unless it is in the notes.
- cautions must match the plan. Do not tell the swimmer to avoid something that appears in the sets.
- If days_to_goal is 14 or less, taper: keep short race-pace work and lower volume late in the week.
- Use session_type "race" ONLY on the goal date, and only if it is in plan_dates.
  Never add races or time trials on other days.
- Only mention body parts, injuries or symptoms that appear in the swimmer's notes.
- distance_m is the full session distance, including warm-up and cool-down, so it is always
  larger than the main set.
- At least one "rest" day. Never more than two hard days (threshold, speed, race_pace) in a row.
- distance_m is in metres. Rest days have distance_m 0 and no main_set.
- main_set is ONE key set in swimmer notation, under 80 characters, for example
  "8x100 free @1:30" or "6x50 fly drill w/ fins". Keep focus under 60 characters.
- You are not a doctor. If there are symptoms, cautions should suggest talking to a coach
  or a medical professional."""


HARD_SESSIONS = {"threshold", "speed", "race_pace", "race"}
_REPS_X_DISTANCE = re.compile(r"(\d+)\s*x\s*(\d+)")  # "10x200", "8 x 50"


def main_set_volume(main_set: str | None) -> int:
    """
    Объём основной серии из строки: "10x200 free @2:30" -> 2000.
    Берём самое большое произведение, а не сумму: в "8x50 broken into 2x25"
    вторая часть описывает ту же серию, а не новую.
    """
    if not main_set:
        return 0
    products = [int(a) * int(b) for a, b in _REPS_X_DISTANCE.findall(main_set)]
    return max(products, default=0)


def hard_days_problems(plan: WeeklyPlan) -> list[str]:
    """Больше двух тяжёлых дней подряд — нарушение правила. Проверяем кодом."""
    in_a_row = 0
    for day in plan.days:
        in_a_row = in_a_row + 1 if day.session_type in HARD_SESSIONS else 0
        if in_a_row > 2:
            return [
                "The plan has more than two hard days in a row (threshold, speed, race_pace, race). "
                "Change at least one of them to easy, aerobic or technique."
            ]
    return []


def main_set_problems(plan: WeeklyPlan) -> list[str]:
    """День не может быть короче своей основной серии."""
    problems = []
    for i, day in enumerate(plan.days, start=1):
        volume = main_set_volume(day.main_set)
        if day.session_type != "rest" and volume > day.distance_m:
            problems.append(
                f"Day {i}: the main set '{day.main_set}' is {volume} m, but distance_m is only "
                f"{day.distance_m}. distance_m is the whole session, so it must be larger."
            )
    return problems


def has_symptom(latest_analysis: dict | None) -> bool:
    """Есть ли в последнем анализе жалоба типа symptom."""
    concerns = (latest_analysis or {}).get("concerns", [])
    return any(c.get("type") == "symptom" for c in concerns)


def cautions_problems(plan: WeeklyPlan, latest_analysis: dict | None) -> list[str]:
    """Если анализ нашёл симптом, неделя без предупреждения — ошибка модели."""
    if has_symptom(latest_analysis) and not plan.cautions:
        return [
            "latest_analysis has a symptom concern, but cautions is null. Write one or two "
            "sentences in cautions: how the plan reduces the load and that the swimmer should "
            "talk to a coach or a medical professional if it continues."
        ]
    return []


def plan_check(notes: list[str | None], latest_analysis: dict | None = None):
    """Все проверки плана для chat_json: части тела, тяжёлые дни, длина серий, предупреждения."""
    body_parts = body_part_check(notes)
    return lambda plan: (
        body_parts(plan)
        + hard_days_problems(plan)
        + main_set_problems(plan)
        + cautions_problems(plan, latest_analysis)
    )


def volume_target(
    metrics: dict, latest_analysis: dict | None, days_to_goal: int | None
) -> dict | None:
    """
    Целевой объём недели. Его считает код, а модель только раскладывает по дням:
    держать число «в процентах от прошлой недели» модели получается плохо.
    """
    base = metrics["volume_last_7d_m"]
    # Меньше четырёх недель истории: «прошлая неделя» может быть одной тренировкой,
    # и цель от неё получится абсурдной (3 км на неделю). Тогда цели нет.
    if not base or metrics["acwr_zone"] == "insufficient_history":
        return None

    concerns = (latest_analysis or {}).get("concerns", [])
    overload = metrics["acwr_zone"] in ("spike", "elevated") or any(
        c.get("type") == "overload" for c in concerns
    )

    if overload:
        low, high, reason = 0.70, 0.80, "reduce after overload"
    elif days_to_goal is not None and 0 <= days_to_goal <= 14:
        low, high, reason = 0.60, 0.80, "taper before the goal event"
    else:
        low, high, reason = 0.90, 1.05, "maintain current load"

    # round(x, -2) округляет до сотен: 16129.4 -> 16100
    return {
        "min": int(round(base * low, -2)),
        "max": int(round(base * high, -2)),
        "reason": reason,
    }


def _context(
    athlete: Athlete,
    history: list[Workout],
    latest: AIRecommendation | None,
    today: date,
    start: date,
) -> dict:
    recent = sorted(history, key=lambda w: w.workout_date, reverse=True)[:7]
    metrics = summarize(history, today)
    days_to_goal = (athlete.goal_date - today).days if athlete.goal_date else None
    latest_analysis = latest.recommendation if latest else None
    return {
        "plan_dates": [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "weekday": (start + timedelta(days=i)).strftime("%a"),
            }
            for i in range(7)
        ],
        "athlete": {
            "main_strokes": athlete.main_strokes,
            "goal_event": athlete.goal_event,
            "goal_date": athlete.goal_date.isoformat() if athlete.goal_date else None,
            "days_to_goal": days_to_goal,
        },
        "metrics": metrics,
        "volume_target_m": volume_target(metrics, latest_analysis, days_to_goal),
        "recent_workouts": [
            {
                "date": w.workout_date.isoformat(),
                "distance_m": to_meters(w.total_distance, w.course),
                "rpe": w.perceived_effort,
                "sets": [_set_line(s) for s in w.sets],
                "notes": w.notes,
                "symptoms": w.symptoms or [],
            }
            for w in recent
        ],
        "latest_analysis": latest_analysis,
    }


def finalize(
    plan: WeeklyPlan,
    start: date,
    last_week_m: int,
    goal_date: date | None = None,
    target: dict | None = None,
    enough_history: bool = True,
) -> dict:
    """
    Проверки и подсчёты кодом после ответа модели:
    даты по порядку, ноль в дни отдыха, старт только в дату цели,
    итог, изменение к прошлой неделе и попадание в целевой объём.

    enough_history=False: меньше четырёх недель истории. Тогда «прошлая неделя»
    может быть одной тренировкой, и процент к ней ничего не значит (+321%).
    """
    for i, day in enumerate(plan.days):
        day.date = start + timedelta(days=i)
        if day.session_type == "race" and day.date != goal_date:
            day.session_type = "race_pace"  # соревнования, которого нет, не ставим
        if day.date == goal_date:
            day.session_type = "race"
        if day.session_type == "rest":
            day.distance_m = 0
            day.main_set = None

    model_total = sum(d.distance_m for d in plan.days)
    model_within = target["min"] <= model_total <= target["max"] if target else None

    scale = None
    if target and not model_within and model_total > 0:
        scale = (target["min"] + target["max"]) / 2 / model_total
        for day in plan.days:
            if day.session_type != "rest":
                floor = math.ceil(main_set_volume(day.main_set) / 100) * 100
                day.distance_m = max(int(round(day.distance_m * scale, -2)), floor)

    total = sum(d.distance_m for d in plan.days)
    change = (
        round((total - last_week_m) / last_week_m * 100)
        if last_week_m and enough_history
        else None
    )
    return {
        **plan.model_dump(mode="json"),
        "total_distance_m": total,
        "last_week_m": last_week_m,
        "change_vs_last_week_pct": change,
        "enough_history": enough_history,
        "volume_target_m": target,
        "model_total_m": model_total,
        "model_within_target": model_within,  # попала ли модель сама: метрика для eval
        "volume_scaled_by": round(scale, 2) if scale else None,
    }


def generate_plan(db: Session, athlete: Athlete) -> AIRecommendation:
    today = date.today()
    start = today + timedelta(days=1)

    history = list(
        db.scalars(
            select(Workout)
            .where(
                Workout.athlete_id == athlete.id,
                Workout.workout_date <= today,
                Workout.workout_date > today - timedelta(days=HISTORY_DAYS),
            )
            .options(selectinload(Workout.sets))
        ).all()
    )

    latest = db.scalars(
        select(AIRecommendation)
        .where(
            AIRecommendation.athlete_id == athlete.id,
            AIRecommendation.kind == Kind.analysis,
        )
        .order_by(AIRecommendation.created_at.desc())
        .limit(1)
    ).first()

    context = _context(athlete, history, latest, today, start)
    notes = grounding_sources(history)
    latest_analysis = context["latest_analysis"]
    plan, raw = chat_json(
        PLAN_SYSTEM,
        json.dumps(context, ensure_ascii=False),
        WeeklyPlan,
        temperature=0.4,
        check=plan_check(notes, latest_analysis),
    )
    warnings = ungrounded_body_parts(plan, notes)
    final = finalize(
        plan,
        start,
        last_week_m=context["metrics"]["volume_last_7d_m"],
        goal_date=athlete.goal_date,
        target=context["volume_target_m"],
        enough_history=context["metrics"]["acwr_zone"] != "insufficient_history",
    )
    # После finalize: он мог поднять объём дня до объёма серии
    rule_warnings = (
        hard_days_problems(plan)
        + main_set_problems(plan)
        + cautions_problems(plan, latest_analysis)
    )

    rec = AIRecommendation(
        athlete_id=athlete.id,
        workout_id=None,
        kind=Kind.plan,
        recommendation={
            **final,
            "grounding_warnings": warnings,
            "rule_warnings": rule_warnings,
        },
        raw_response=raw,
        model=settings.llm_name,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
