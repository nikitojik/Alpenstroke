from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AthleteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    main_strokes: list[str] = []
    goal_event: str | None = None
    goal_date: date | None = None


class AthleteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    main_strokes: list[str] | None = None
    goal_event: str | None = None
    goal_date: date | None = None

    @field_validator("name", "main_strokes")
    @classmethod
    def not_null(cls, value):

        if value is None:
            raise ValueError("cannot be null")
        return value


class AthleteOut(AthleteCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
