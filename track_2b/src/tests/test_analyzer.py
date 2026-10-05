from datetime import date, timedelta

from app.models import Athlete, Course, Set, Stroke, Workout
from app.schemas.analysis import Analysis
from app.services.analyzer import RECENT_FOR_PROMPT, build_context, enforce_confidence

TODAY = date(2026, 10, 3)


def make_athlete() -> Athlete:
    return Athlete(
        name="Private Name",
        main_strokes=["fly"],
        goal_event="100 fly",
        goal_date=TODAY + timedelta(days=21),
    )


def make_workout(days_ago: int, notes: str | None = None) -> Workout:
    return Workout(
        workout_date=TODAY - timedelta(days=days_ago),
        course=Course.SCY,
        duration_min=90,
        total_distance=1000,
        perceived_effort=6,
        notes=notes,
        sets=[Set(stroke=Stroke.fly, distance=50, reps=8, interval_s=55)],
    )


def test_context_has_three_layers():
    ctx = build_context(make_athlete(), [make_workout(0)], TODAY)
    assert set(ctx) == {"athlete", "metrics", "recent_workouts"}
    assert ctx["athlete"]["days_to_goal"] == 21


def test_notes_reach_the_model():
    ctx = build_context(
        make_athlete(), [make_workout(0, notes="calf cramp on fly")], TODAY
    )
    assert ctx["recent_workouts"][0]["notes"] == "calf cramp on fly"


def test_name_is_not_sent_to_model():
    ctx = build_context(make_athlete(), [make_workout(0)], TODAY)
    assert "Private Name" not in str(ctx)


def test_yards_are_converted_and_sets_are_compact():
    w = build_context(make_athlete(), [make_workout(0)], TODAY)["recent_workouts"][0]
    assert w["distance_m"] == 914
    assert w["sets"] == ["8x50 fly @55s"]


def test_only_recent_workouts_newest_first():
    workouts = [make_workout(i) for i in range(30)]
    recent = build_context(make_athlete(), workouts, TODAY)["recent_workouts"]
    assert len(recent) == RECENT_FOR_PROMPT
    assert recent[0]["date"] == TODAY.isoformat()


def test_confidence_is_low_without_four_weeks_of_history():
    analysis = Analysis(
        summary="s", concerns=[], recommendation="r", confidence="medium"
    )
    assert enforce_confidence(analysis, "insufficient_history").confidence == "low"


def test_confidence_is_kept_with_enough_history():
    analysis = Analysis(summary="s", concerns=[], recommendation="r", confidence="high")
    assert enforce_confidence(analysis, "optimal").confidence == "high"
