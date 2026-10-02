from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AthleteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    main_strokes: list[str] = []
    goal_event: str | None = None
    goal_date: date | None = None


class AthleteOut(AthleteCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
