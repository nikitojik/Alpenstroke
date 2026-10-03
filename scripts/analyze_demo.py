from sqlalchemy import select

from app.db import SessionLocal
from app.models import Athlete, Workout
from app.services.analyzer import analyze_workout
from scripts.seed import DEMO_PREFIX

EXPECTED = {
    "Demo: Steady": "no overload or symptom concerns",
    "Demo: Spike": "overload",
    "Demo: Cramps": "symptom",
}


def main() -> None:
    with SessionLocal() as db:
        athletes = db.scalars(
            select(Athlete).where(Athlete.name.startswith(DEMO_PREFIX)).order_by(Athlete.id)
        ).all()
        if not athletes:
            print("No demo athletes. Run: python -m scripts.seed")
            return

        for athlete in athletes:
            latest = db.scalars(
                select(Workout)
                .where(Workout.athlete_id == athlete.id)
                .order_by(Workout.workout_date.desc())
                .limit(1)
            ).one()
            rec = analyze_workout(db, latest)
            result = rec.recommendation

            print(f"\n=== {athlete.name}  (expected: {EXPECTED.get(athlete.name, '?')})")
            print(f"confidence: {result['confidence']}")
            print(f"summary: {result['summary']}")
            for c in result["concerns"]:
                print(f"  - [{c['type']}] {c['detail']}")
            if not result["concerns"]:
                print("  - no concerns")
            print(f"recommendation: {result['recommendation']}")


if __name__ == "__main__":
    main()