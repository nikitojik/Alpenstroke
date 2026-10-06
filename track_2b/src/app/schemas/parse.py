from pydantic import BaseModel, Field, field_validator

from app.models import Course
from app.schemas.workout import SetIn


class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    course: Course | None = None


class ExtractedSet(SetIn):
    source: str | None = None


class WorkoutExtraction(BaseModel):
    course: Course | None = None
    duration_min: int | None = Field(default=None, gt=0)
    perceived_effort: int | None = Field(default=None, ge=1, le=10)
    sets: list[ExtractedSet] = []
    symptoms: list[str] = []
    notes: str | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def notes_as_text(cls, value):
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        return value or None


class ParsedWorkout(WorkoutExtraction):
    total_distance: int | None = Field(default=None, gt=0)


class ParseResponse(ParsedWorkout):
    missing: list[str] = []
