from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models import Kind

ConcernType = Literal["overload", "undertraining", "symptom", "taper", "other"]


class Concern(BaseModel):
    type: ConcernType
    detail: str


class Analysis(BaseModel):
    summary: str
    concerns: list[Concern]
    recommendation: str
    confidence: Literal["low", "medium", "high"]


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    athlete_id: int
    workout_id: int | None
    kind: Kind
    recommendation: dict
    model: str
    created_at: datetime
    was_helpful: bool | None