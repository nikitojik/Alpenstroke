from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Athlete, Workout
from app.schemas.analysis import RecommendationOut
from app.schemas.parse import ParseRequest, ParseResponse
from app.schemas.workout import WorkoutCreate, WorkoutOut
from app.services.analyzer import analyze_workout
from app.services.llm import LLMError
from app.services.parser import parse_workout_text
from app.services.workouts import save_workout

router = APIRouter(prefix="/workouts", tags=["workouts"])


@router.post("/parse", response_model=ParseResponse)
def parse_workout(payload: ParseRequest):
    """Текст тренировки → черновик. Ничего не сохраняет: пользователь сначала проверяет."""
    try:
        return parse_workout_text(payload.text, payload.course)
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
def create_workout(payload: WorkoutCreate, db: Session = Depends(get_db)):
    if db.get(Athlete, payload.athlete_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Athlete not found")
    return save_workout(db, payload)


@router.get("", response_model=list[WorkoutOut])
def list_workouts(
    athlete_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Workout)
        .where(Workout.athlete_id == athlete_id)
        .order_by(Workout.workout_date.desc(), Workout.id.desc())
        .limit(limit)
        .options(selectinload(Workout.sets))
    )
    return db.scalars(stmt).all()


def get_workout_or_404(db: Session, workout_id: int) -> Workout:
    workout = db.get(Workout, workout_id)
    if workout is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout not found")
    return workout


@router.get("/{workout_id}", response_model=WorkoutOut)
def get_workout(workout_id: int, db: Session = Depends(get_db)):
    return get_workout_or_404(db, workout_id)


@router.post("/{workout_id}/analyze", response_model=RecommendationOut)
def analyze(workout_id: int, db: Session = Depends(get_db)):
    workout = get_workout_or_404(db, workout_id)
    try:
        return analyze_workout(db, workout)
    except LLMError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: int, db: Session = Depends(get_db)):
    # Подходы и рекомендации к этой тренировке удалятся каскадом
    db.delete(get_workout_or_404(db, workout_id))
    db.commit()
