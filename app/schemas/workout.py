from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Course, Stroke


class SetIn(BaseModel):
    stroke: Stroke
    distance: int = Field(gt=0)
    reps: int = Field(default=1, gt=0)
    interval_s: int | None = Field(default=None, gt=0)
    rest_s: int | None = Field(default=None, ge=0)


class SetOut(SetIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class WorkoutCreate(BaseModel):
    athlete_id: int
    workout_date: date
    course: Course
    duration_min: int = Field(gt=0, le=600)
    total_distance: int = Field(gt=0)
    perceived_effort: int = Field(ge=1, le=10)
    notes: str | None = None
    symptoms: list[str] = []
    sets: list[SetIn] = []


class WorkoutOut(WorkoutCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    sets: list[SetOut] = []
