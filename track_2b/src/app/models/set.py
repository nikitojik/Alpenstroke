import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.workout import Workout


class Stroke(enum.Enum):
    freestyle = "freestyle"
    fly = "fly"
    breaststroke = "breaststroke"
    backstroke = "backstroke"
    medley = "medley"
    choice = "choice"


class Set(Base):
    __tablename__ = "sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"))
    stroke: Mapped[Stroke] = mapped_column(Enum(Stroke))
    distance: Mapped[int]  # единицы берутся из workout.course
    reps: Mapped[int]
    interval_s: Mapped[int | None]
    rest_s: Mapped[int | None]

    workout: Mapped["Workout"] = relationship(back_populates="sets")