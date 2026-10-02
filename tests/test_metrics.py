from dataclasses import dataclass
from datetime import date, timedelta

from app.models import Course
from app.services.metrics import (
    acute_chronic_ratio,
    acwr_zone,
    daily_loads,
    session_load,
    summarize,
    to_meters,
    volume_m,
)

TODAY = date(2026, 10, 2)


@dataclass
class W:
    """Простая замена ORM-модели Workout для тестов."""
    workout_date: date
    course: Course = Course.SCM
    total_distance: int = 4000
    duration_min: int = 60
    perceived_effort: int = 5


def every_day(days: int, **kwargs) -> list[W]:
    """Тренировка каждый день в течение `days` дней, заканчивая TODAY."""
    return [W(TODAY - timedelta(days=i), **kwargs) for i in range(days)]


# ---------- базовые функции ----------

def test_session_load():
    assert session_load(perceived_effort=7, duration_min=60) == 420


def test_to_meters_converts_yards_only():
    assert to_meters(100, Course.SCY) == 91
    assert to_meters(100, Course.SCM) == 100
    assert to_meters(100, Course.LCM) == 100


def test_two_workouts_same_day_add_up():
    loads = daily_loads([W(TODAY, duration_min=60), W(TODAY, duration_min=30)])
    assert loads == {TODAY: 5 * 60 + 5 * 30}


# ---------- объём ----------

def test_volume_window_is_7_days_inclusive():
    workouts = [
        W(TODAY, total_distance=1000),
        W(TODAY - timedelta(days=6), total_distance=1000),  # ещё внутри окна
        W(TODAY - timedelta(days=7), total_distance=1000),  # уже снаружи
    ]
    assert volume_m(workouts, TODAY) == 2000


def test_volume_mixes_yards_and_meters_correctly():
    workouts = [W(TODAY, course=Course.SCY, total_distance=1000),
                W(TODAY, course=Course.SCM, total_distance=1000)]
    assert volume_m(workouts, TODAY) == 914 + 1000


# ---------- ACWR ----------

def test_acwr_none_with_short_history():
    assert acute_chronic_ratio(every_day(20), TODAY) is None


def test_acwr_steady_training_is_one():
    assert acute_chronic_ratio(every_day(28), TODAY) == 1.0


def test_acwr_detects_spike():
    base = every_day(28, perceived_effort=4)
    # Последняя неделя тяжелее: RPE 9 вместо 4
    for w in base[:7]:
        w.perceived_effort = 9
    ratio = acute_chronic_ratio(base, TODAY)
    assert ratio > 1.5
    assert acwr_zone(ratio) == "spike"


def test_acwr_counts_rest_days_as_zero():
    base = every_day(28)
    # Убираем 4 из 7 тренировок последней недели: острая нагрузка должна упасть
    rested = base[7:] + base[:3]
    ratio = acute_chronic_ratio(rested, TODAY)
    assert ratio < 0.8
    assert acwr_zone(ratio) == "low"


def test_acwr_zones():
    assert acwr_zone(None) == "insufficient_history"
    assert acwr_zone(1.0) == "optimal"
    assert acwr_zone(1.4) == "elevated"


# ---------- сводка для промпта ----------

def test_summarize_shape():
    s = summarize(every_day(35), TODAY)
    assert s["sessions_last_7d"] == 7
    assert s["volume_last_7d_m"] == 7 * 4000
    assert s["volume_prev_7d_m"] == 7 * 4000
    assert s["avg_rpe_last_7d"] == 5.0
    assert s["acwr_zone"] == "optimal"


def test_summarize_with_no_workouts():
    s = summarize([], TODAY)
    assert s["sessions_last_7d"] == 0
    assert s["avg_rpe_last_7d"] is None
    assert s["acwr_zone"] == "insufficient_history"