from datetime import date, datetime
from typing import TYPE_CHECKING
 
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
 
from app.db import Base
 
if TYPE_CHECKING:  # только для подсказок редактора, при запуске не выполняется
    from app.models.workout import Workout
 
 
class Athlete(Base):
    __tablename__ = "athletes"
 
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    main_strokes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    goal_event: Mapped[str | None] = mapped_column(String(100))
    goal_date: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
 
    workouts: Mapped[list["Workout"]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
 