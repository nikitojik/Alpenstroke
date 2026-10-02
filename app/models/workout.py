import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.athlete import Athlete
    from app.models.set import Set


class Course(enum.Enum):
    SCY = "SCY"  # short course yards, 25 yd
    SCM = "SCM"  # short course meters, 25 m
    LCM = "LCM"  # long course meters, 50 m


class Workout(Base):
    __tablename__ = "workouts"
    __table_args__ = (
        CheckConstraint("perceived_effort BETWEEN 1 AND 10", name="ck_workouts_rpe_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id", ondelete="CASCADE"))
    workout_date: Mapped[date]
    course: Mapped[Course] = mapped_column(Enum(Course))
    duration_min: Mapped[int]
    total_distance: Mapped[int]  # в единицах course: ярды для SCY, метры для SCM/LCM
    perceived_effort: Mapped[int]  # RPE 1-10
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    athlete: Mapped["Athlete"] = relationship(back_populates="workouts")
    sets: Mapped[list["Set"]] = relationship(
        back_populates="workout", cascade="all, delete-orphan"
    )