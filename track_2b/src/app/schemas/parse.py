from pydantic import BaseModel, Field, field_validator

from app.models import Course, Stroke
from app.schemas.workout import SetIn
from app.services.set_rules import strokes_in


class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    course: Course | None = None


class ExtractedSet(SetIn):
    stroke: Stroke | None = None
    source: str | None = None

    @field_validator("stroke", mode="before")
    @classmethod
    def stroke_in_any_spelling(cls, value):
        if value is None or isinstance(value, Stroke):
            return value
        text = str(value).strip().lower()
        try:
            return Stroke(text)
        except ValueError:
            named = strokes_in(text)  # тот же словарь, что для цитат
            return named.pop() if len(named) == 1 else None


class WorkoutExtraction(BaseModel):
    """
    Что возвращает модель. Здесь нет total_distance: сумму считает код по сериям,
    а модель, если её попросить, иногда пишет арифметику ("400 + 3000"), и это ломает JSON.
    """

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
    """Черновик тренировки после кода: с итоговой дистанцией."""

    total_distance: int | None = Field(default=None, gt=0)


class ParseResponse(ParsedWorkout):
    missing: list[str] = []
