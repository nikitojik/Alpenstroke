"""Тесты того, что код делает с планом до и после ответа модели. Без сети и базы."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.plan import PlanDay, WeeklyPlan
from app.services.planner import (
    cautions_problems,
    finalize,
    hard_days_problems,
    main_set_problems,
    main_set_volume,
    volume_target,
)

START = date(2026, 10, 4)


def make_plan(days: list[tuple[str, int]], wrong_dates: bool = False) -> WeeklyPlan:
    return WeeklyPlan(
        summary="s",
        days=[
            PlanDay(
                # модель может ошибиться в датах: проверим, что код их исправит
                date=date(2000, 1, 1) if wrong_dates else START + timedelta(days=i),
                session_type=kind,
                distance_m=dist,
                main_set="8x100 free @1:30",
                focus="f",
            )
            for i, (kind, dist) in enumerate(days)
        ],
    )


# сумма 19 000 м
WEEK = [("aerobic", 4000), ("threshold", 4500), ("rest", 0), ("easy", 3000),
        ("speed", 3500), ("aerobic", 4000), ("rest", 0)]


# ---------- finalize: правка ответа модели ----------

def test_dates_are_assigned_by_code():
    result = finalize(make_plan(WEEK, wrong_dates=True), START, last_week_m=0)
    assert [d["date"] for d in result["days"]] == [
        (START + timedelta(days=i)).isoformat() for i in range(7)
    ]


def test_rest_days_have_no_distance_or_main_set():
    week = WEEK.copy()
    week[2] = ("rest", 2000)  # модель поставила объём в день отдыха
    result = finalize(make_plan(week), START, last_week_m=0)
    assert result["days"][2]["distance_m"] == 0
    assert result["days"][2]["main_set"] is None


def test_invented_race_is_downgraded():
    week = WEEK.copy()
    week[6] = ("race", 1500)  # старта в эту неделю нет
    result = finalize(make_plan(week), START, last_week_m=0, goal_date=date(2026, 10, 24))
    assert result["days"][6]["session_type"] == "race_pace"


def test_goal_date_inside_week_becomes_race():
    goal = START + timedelta(days=5)
    result = finalize(make_plan(WEEK), START, last_week_m=0, goal_date=goal)
    assert result["days"][5]["session_type"] == "race"


def test_change_vs_last_week():
    result = finalize(make_plan(WEEK), START, last_week_m=23000)
    assert result["total_distance_m"] == 19000
    assert result["change_vs_last_week_pct"] == -17


def test_change_is_none_without_last_week():
    assert finalize(make_plan(WEEK), START, last_week_m=0)["change_vs_last_week_pct"] is None


def test_plan_must_have_exactly_seven_days():
    with pytest.raises(ValidationError):
        make_plan(WEEK[:6])


# ---------- finalize: доведение объёма до цели ----------

def test_no_scaling_when_model_hits_target():
    target = {"min": 18000, "max": 20000, "reason": "r"}
    result = finalize(make_plan(WEEK), START, last_week_m=23000, target=target)
    assert result["model_within_target"] is True
    assert result["volume_scaled_by"] is None
    assert result["total_distance_m"] == 19000


def test_scaling_brings_total_into_target():
    # Модель запланировала 19 000 м, а цель 25 400-29 000 (как у Spike)
    target = {"min": 25400, "max": 29000, "reason": "r"}
    result = finalize(make_plan(WEEK), START, last_week_m=36300, target=target)
    assert result["model_within_target"] is False
    assert result["model_total_m"] == 19000
    assert target["min"] <= result["total_distance_m"] <= target["max"]
    assert result["volume_scaled_by"] == pytest.approx(1.43, abs=0.01)


def test_scaling_keeps_rest_days_at_zero_and_keeps_proportions():
    target = {"min": 25400, "max": 29000, "reason": "r"}
    days = finalize(make_plan(WEEK), START, last_week_m=36300, target=target)["days"]
    assert days[2]["distance_m"] == 0 and days[6]["distance_m"] == 0
    # самый тяжёлый день модели (threshold) остаётся самым тяжёлым
    assert max(days, key=lambda d: d["distance_m"])["session_type"] == "threshold"


# ---------- volume_target: число считает код ----------

def metrics(volume: int, zone: str = "optimal") -> dict:
    return {"volume_last_7d_m": volume, "acwr_zone": zone}


def test_target_maintain_when_all_is_fine():
    t = volume_target(metrics(20000), None, days_to_goal=35)
    assert (t["min"], t["max"]) == (18000, 21000)


def test_target_reduce_on_spike_even_without_analysis():
    t = volume_target(metrics(36300, "spike"), None, days_to_goal=21)
    assert (t["min"], t["max"]) == (25400, 29000)
    assert "overload" in t["reason"]


def test_target_reduce_on_overload_in_analysis():
    analysis = {"concerns": [{"type": "overload", "detail": "..."}]}
    t = volume_target(metrics(20000), analysis, days_to_goal=35)
    assert t["max"] == 16000


def test_target_taper_close_to_goal():
    t = volume_target(metrics(20000), None, days_to_goal=10)
    assert "taper" in t["reason"]


def test_no_target_without_history():
    assert volume_target(metrics(0, "insufficient_history"), None, days_to_goal=None) is None


# ---------- правило: не больше двух тяжёлых дней подряд ----------

def test_three_hard_days_in_a_row_is_a_problem():
    # как в прогоне Spike: threshold, threshold, race_pace
    week = [("rest", 0), ("easy", 4000), ("technique", 4000), ("aerobic", 4000),
            ("threshold", 4000), ("threshold", 4000), ("race_pace", 3000)]
    assert len(hard_days_problems(make_plan(week))) == 1


def test_two_hard_days_in_a_row_are_fine():
    # в WEEK тяжёлые дни разделены отдыхом и лёгкими днями
    assert hard_days_problems(make_plan(WEEK)) == []


def test_rest_day_may_have_no_focus():
    # модель ставит focus: null в день отдыха, это нормальный ответ
    day = PlanDay(date=START, session_type="rest", distance_m=0, focus=None)
    assert day.focus is None


# ---------- объём основной серии ----------

def test_main_set_volume_parses_swimmer_notation():
    assert main_set_volume("10x200 freestyle @2:30") == 2000
    assert main_set_volume("8 x 50 fly drill w/ fins") == 400
    assert main_set_volume("8x50 broken into 2x25") == 400  # вторая часть описывает ту же серию
    assert main_set_volume("easy swim") == 0
    assert main_set_volume(None) == 0


def test_day_shorter_than_its_main_set_is_a_problem():
    # как в прогоне Nikita: 10x200 = 2000 м в день на 600 м
    plan = make_plan(WEEK)
    plan.days[3].main_set = "10x200 freestyle @2:30"
    plan.days[3].distance_m = 600
    problems = main_set_problems(plan)
    assert len(problems) == 1 and "2000" in problems[0]


def test_scaling_never_shrinks_a_day_below_its_main_set():
    plan = make_plan(WEEK)
    plan.days[0].main_set = "10x200 freestyle @2:30"  # 2000 м
    target = {"min": 3000, "max": 3600, "reason": "r"}  # абсурдно маленькая цель
    days = finalize(plan, START, last_week_m=3400, target=target)["days"]
    assert days[0]["distance_m"] >= 2000


def test_no_target_with_short_history_even_if_last_week_has_volume():
    # одна тренировка 3400 м: «прошлая неделя» есть, но истории меньше четырёх недель
    assert volume_target(metrics(3400, "insufficient_history"), None, days_to_goal=41) is None


# ---------- короткая история и предупреждения ----------

def test_no_change_pct_with_short_history():
    # как у Nikita: одна тренировка 3400 м, план 14.3 км -> «+321%» ничего не значит
    result = finalize(make_plan(WEEK), START, last_week_m=3400, enough_history=False)
    assert result["change_vs_last_week_pct"] is None
    assert result["enough_history"] is False


SYMPTOM = {"concerns": [{"type": "symptom", "detail": "shoulder pain on fly"}]}


def test_symptom_without_cautions_is_a_problem():
    assert len(cautions_problems(make_plan(WEEK), SYMPTOM)) == 1


def test_symptom_with_cautions_is_fine():
    plan = make_plan(WEEK)
    plan.cautions = "Fly is in short repeats; talk to a coach if the shoulder pain continues."
    assert cautions_problems(plan, SYMPTOM) == []


def test_no_symptom_needs_no_cautions():
    assert cautions_problems(make_plan(WEEK), {"concerns": []}) == []
    assert cautions_problems(make_plan(WEEK), None) == []