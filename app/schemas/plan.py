from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

SessionType = Literal[
    "rest", "easy", "technique", "aerobic", "threshold", "speed", "race_pace", "race"
]


class PlanDay(BaseModel):
    date: date
    session_type: SessionType
    distance_m: int = Field(ge=0)
    main_set: str | None = None  # в нотации пловца: "8x100 free @1:30"
    focus: str | None = None     # зачем эта тренировка; у дня отдыха может быть пустым


class WeeklyPlan(BaseModel):
    """Что модель должна вернуть. Ровно 7 дней: длину проверяет сама схема."""

    summary: str
    days: list[PlanDay] = Field(min_length=7, max_length=7)
    cautions: str | None = None