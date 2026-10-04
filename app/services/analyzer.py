import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import AIRecommendation, Athlete, Kind, Workout
from app.schemas.analysis import Analysis
from app.services.grounding import body_part_check, ungrounded_body_parts
from app.services.llm import chat_json
from app.services.metrics import summarize, to_meters

HISTORY_DAYS = 42      # хватает на 28-дневное окно ACWR с запасом
RECENT_FOR_PROMPT = 14  # сколько последних тренировок показываем модели целиком

ANALYZE_SYSTEM = """You are an experienced swim coach with a background in sports science.
You review a swimmer's recent training and give practical advice.

You receive JSON with:
- "metrics": training-load numbers computed by code. Trust them, do not recalculate.
  acwr = acute:chronic workload ratio. acwr_zone is low / optimal / elevated / spike / insufficient_history.
- "recent_workouts": the latest sessions, newest first, with sets and the swimmer's own notes.
- "athlete": main strokes, goal event and days until it.

Rules:
- acwr_zone "spike" or "elevated" means a concern of type "overload".
- acwr_zone "low" close to the goal event may be an intentional taper (type "taper"), not a problem.
- Read the notes. Recurring pain, cramps or illness is a concern of type "symptom".
  Link it to a stroke or set when the notes allow it.
- ONLY IF you report a "symptom" concern tied to a stroke: reduce the load on that stroke
  (short repeats, drills, broken sets, fins, more rest) instead of removing it completely,
  especially if it is the stroke of the athlete's goal event.
  Without a symptom concern, do not suggest reducing or replacing any stroke.
- If nothing is wrong, return an empty concerns list and recommend continuing the current plan.
  Do not invent problems.
- Every change you recommend must address one of the listed concerns.
- Only mention body parts, injuries or symptoms that appear in the swimmer's notes.
- Keep total volume unchanged unless there is an "overload" concern.
- The recommendation must be concrete and cover the next 3-7 days, with numbers
  (for example "cut volume by about 20%" or "replace fly sets with freestyle for a week").
- You are not a doctor. For recurring pain or cramps, also suggest talking to a coach
  or a medical professional.
- Distances are in metres.
- Use confidence "low" when acwr_zone is insufficient_history."""


def _set_line(s) -> str:
    """Компактная запись подхода: '10x100 freestyle @90s'. Экономит токены."""
    line = f"{s.reps}x{s.distance} {s.stroke.value}"
    if s.interval_s:
        line += f" @{s.interval_s}s"
    if s.rest_s:
        line += f" rest {s.rest_s}s"
    return line


def build_context(athlete: Athlete, workouts: list[Workout], on: date) -> dict:
    """Собирает данные для промпта. Имя спортсмена модели не отправляем: оно ей не нужно."""
    recent = sorted(workouts, key=lambda w: w.workout_date, reverse=True)[:RECENT_FOR_PROMPT]
    return {
        "athlete": {
            "main_strokes": athlete.main_strokes,
            "goal_event": athlete.goal_event,
            "days_to_goal": (athlete.goal_date - on).days if athlete.goal_date else None,
        },
        "metrics": summarize(workouts, on),
        "recent_workouts": [
            {
                "date": w.workout_date.isoformat(),
                "pool": w.course.value,
                "distance_m": to_meters(w.total_distance, w.course),
                "duration_min": w.duration_min,
                "rpe": w.perceived_effort,
                "sets": [_set_line(s) for s in w.sets],
                "notes": w.notes,
            }
            for w in recent
        ],
    }


def analyze_workout(db: Session, workout: Workout) -> AIRecommendation:
    on = workout.workout_date
    history = db.scalars(
        select(Workout)
        .where(
            Workout.athlete_id == workout.athlete_id,
            Workout.workout_date <= on,
            Workout.workout_date > on - timedelta(days=HISTORY_DAYS),
        )
        .options(selectinload(Workout.sets))
    ).all()

    context = build_context(workout.athlete, list(history), on)
    notes = [w.notes for w in history]
    analysis, raw = chat_json(
        ANALYZE_SYSTEM,
        json.dumps(context, ensure_ascii=False),
        Analysis,
        temperature=0.3,
        check=body_part_check(notes),
    )

    rec = AIRecommendation(
        athlete_id=workout.athlete_id,
        workout_id=workout.id,
        kind=Kind.analysis,
        recommendation={
            **analysis.model_dump(),
            # если модель не исправилась и со второй попытки, это видно здесь
            "grounding_warnings": ungrounded_body_parts(analysis, notes),
        },
        raw_response=raw,
        model=settings.apertus_model,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec