from collections import defaultdict
from datetime import date, timedelta
from typing import Protocol

from app.models import Course

YARD_TO_M = 0.9144
ACUTE_DAYS = 7
CHRONIC_DAYS = 28


class WorkoutLike(Protocol):
    workout_date: date
    course: Course
    total_distance: int
    duration_min: int
    perceived_effort: int


def to_meters(distance: int, course: Course) -> int:
    if course == Course.SCY:
        return round(distance * YARD_TO_M)
    return distance


def session_load(perceived_effort: int, duration_min: int) -> int:
    return perceived_effort * duration_min


def daily_loads(workouts):
    loads = defaultdict(int)
    for w in workouts:
        loads[w.workout_date] += session_load(w.perceived_effort, w.duration_min)
    return dict(loads)


def _in_window(day, end, days):
    return end - timedelta(days=days - 1) <= day <= end


def volume_m(workouts, end, days=ACUTE_DAYS):
    return sum(
        to_meters(w.total_distance, w.course)
        for w in workouts
        if _in_window(w.workout_date, end, days)
    )


def acute_chronic_ratio(workouts, on):
    loads = daily_loads(workouts)
    if not loads or min(loads) > on - timedelta(days=CHRONIC_DAYS - 1):
        return None

    acute = (
        sum(v for d, v in loads.items() if _in_window(d, on, ACUTE_DAYS)) / ACUTE_DAYS
    )
    chronic = (
        sum(v for d, v in loads.items() if _in_window(d, on, CHRONIC_DAYS))
        / CHRONIC_DAYS
    )
    if chronic == 0:
        return None
    return round(acute / chronic, 2)


def acwr_zone(ratio: float | None) -> str:
    if ratio is None:
        return "insufficient_history"
    if ratio < 0.8:
        return "low"
    if ratio <= 1.3:
        return "optimal"
    if ratio <= 1.5:
        return "elevated"
    return "spike"


def summarize(workouts: list[WorkoutLike], on: date) -> dict:
    ratio = acute_chronic_ratio(workouts, on)
    last_7 = [w for w in workouts if _in_window(w.workout_date, on, ACUTE_DAYS)]
    return {
        "as_of": on.isoformat(),
        "sessions_last_7d": len(last_7),
        "volume_last_7d_m": volume_m(workouts, on, ACUTE_DAYS),
        "volume_prev_7d_m": volume_m(
            workouts, on - timedelta(days=ACUTE_DAYS), ACUTE_DAYS
        ),
        "load_last_7d": sum(
            session_load(w.perceived_effort, w.duration_min) for w in last_7
        ),
        "avg_rpe_last_7d": (
            round(sum(w.perceived_effort for w in last_7) / len(last_7), 1)
            if last_7
            else None
        ),
        "acwr": ratio,
        "acwr_zone": acwr_zone(ratio),
    }
