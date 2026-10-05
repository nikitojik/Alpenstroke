"""Сохранение тренировки. Вызывают и JSON API, и HTML-страница: код один."""

from sqlalchemy.orm import Session

from app.models import Set, Workout
from app.schemas.workout import WorkoutCreate


def save_workout(db: Session, payload: WorkoutCreate) -> Workout:
    workout = Workout(**payload.model_dump(exclude={"sets"}))
    workout.sets = [Set(**s.model_dump()) for s in payload.sets]
    db.add(workout)  # подходы сохранятся вместе с тренировкой (cascade)
    db.commit()
    db.refresh(workout)
    return workout
