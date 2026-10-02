from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Athlete
from app.schemas.athlete import AthleteCreate, AthleteOut, AthleteUpdate

router = APIRouter(prefix="/athletes", tags=["athletes"])


def get_athlete_or_404(db: Session, athlete_id: int) -> Athlete:
    athlete = db.get(Athlete, athlete_id)
    if athlete is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Athlete not found"
        )
    return athlete


@router.post("", response_model=AthleteOut, status_code=status.HTTP_201_CREATED)
def create_athlete(payload: AthleteCreate, db: Session = Depends(get_db)):
    athlete = Athlete(**payload.model_dump())
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete


@router.get("", response_model=list[AthleteOut])
def list_athletes(db: Session = Depends(get_db)):
    return db.scalars(select(Athlete).order_by(Athlete.id)).all()


@router.get("/{athlete_id}", response_model=AthleteOut)
def get_athlete(athlete_id: int, db: Session = Depends(get_db)):
    return get_athlete_or_404(db, athlete_id)


@router.patch("/{athlete_id}", response_model=AthleteOut)
def update_athlete(
    athlete_id: int, payload: AthleteUpdate, db: Session = Depends(get_db)
):
    athlete = get_athlete_or_404(db, athlete_id)
    # exclude_unset: только поля, которые клиент реально прислал
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(athlete, field, value)
    db.commit()
    db.refresh(athlete)
    return athlete
