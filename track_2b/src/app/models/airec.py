import enum
from datetime import datetime
 
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
 
from app.db import Base
 
 
class Kind(enum.Enum):
    analysis = "analysis"
    plan = "plan"
 
 
class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"
 
    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    # None для недельного плана: он не привязан к одной тренировке
    workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("workouts.id", ondelete="CASCADE")
    )
    kind: Mapped[Kind] = mapped_column(Enum(Kind))
    recommendation: Mapped[dict] = mapped_column(JSONB)
    raw_response: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    was_helpful: Mapped[bool | None]
 