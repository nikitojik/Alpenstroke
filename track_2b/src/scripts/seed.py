import argparse
import random
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import Athlete, Course, Set, Stroke, Workout
from app.services.metrics import summarize

DAYS = 42
REST_WEEKDAY = 6  # воскресенье — выходной
DEMO_PREFIX = "Demo:"

CRAMP_NOTES = [
    "calf cramp on the fly set",
    "left calf cramped again during fly 50s",
    "calf cramp, had to stop the last two fly reps",
    "cramping in both calves on fly, stretched it out",
]


# ---------- сборка одной тренировки ----------


def build_sets(main_reps: int, fly_reps: int) -> list[Set]:
    return [
        Set(stroke=Stroke.choice, distance=400, reps=1),  # разминка
        Set(
            stroke=Stroke.freestyle, distance=100, reps=main_reps, interval_s=90
        ),  # основная серия
        Set(stroke=Stroke.fly, distance=50, reps=fly_reps, interval_s=55),
        Set(stroke=Stroke.choice, distance=200, reps=1),  # заминка
    ]


def make_workout(
    day: date,
    course: Course,
    main_reps: int,
    fly_reps: int,
    duration: int,
    rpe: int,
    notes: str | None = None,
    symptoms: list[str] | None = None,
) -> Workout:
    sets = build_sets(main_reps, fly_reps)
    return Workout(
        workout_date=day,
        course=course,
        duration_min=duration,
        total_distance=sum(s.distance * s.reps for s in sets),
        perceived_effort=rpe,
        notes=notes,
        symptoms=symptoms or [],
        sets=sets,
    )


def training_days(end: date) -> list[date]:
    start = end - timedelta(days=DAYS - 1)
    days = [start + timedelta(days=i) for i in range(DAYS)]
    return [d for d in days if d.weekday() != REST_WEEKDAY]


# ---------- три профиля ----------


def steady(rng: random.Random, end: date) -> list[Workout]:
    return [
        make_workout(
            d,
            Course.SCY,
            rng.randint(28, 34),
            8,
            rng.randint(80, 95),
            rng.choice([5, 6, 6, 7]),
        )
        for d in training_days(end)
    ]


def spike(rng: random.Random, end: date) -> list[Workout]:
    workouts = []
    for d in training_days(end):
        if (end - d).days < 7:  # последняя неделя: больше объём, дольше, тяжелее
            workouts.append(
                make_workout(
                    d,
                    Course.SCM,
                    rng.randint(44, 50),
                    12,
                    rng.randint(125, 140),
                    rng.choice([8, 9, 9]),
                )
            )
        else:
            workouts.append(
                make_workout(
                    d,
                    Course.SCM,
                    rng.randint(28, 34),
                    8,
                    rng.randint(80, 95),
                    rng.choice([5, 6, 6]),
                )
            )
    return workouts


def cramps(rng: random.Random, end: date) -> list[Workout]:
    workouts = []
    for d in training_days(end):
        recent = (end - d).days < 14
        notes = rng.choice(CRAMP_NOTES) if recent and rng.random() < 0.6 else None
        workouts.append(
            make_workout(
                d,
                Course.LCM,
                rng.randint(28, 34),
                10,
                rng.randint(80, 95),
                rng.choice([6, 6, 7]),
                notes,
                symptoms=["calf cramp"] if notes else None,
            )
        )
    return workouts


# имя, стили, цель, недель до старта, функция-профиль, зерно генератора
PROFILES = [
    ("Steady", ["freestyle"], "200 free", 5, steady, 1),
    ("Spike", ["freestyle"], "100 free", 3, spike, 2),
    ("Cramps", ["fly"], "100 fly", 4, cramps, 3),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create three demo athletes with six weeks of workouts.")
    parser.add_argument(
        "--if-empty", action="store_true",
        help="do nothing if the database already has athletes (used on container start)",
    )
    args = parser.parse_args()

    end = date.today()
    with SessionLocal() as db:
        # При запуске контейнера: демо-данные нужны только на пустой базе,
        # иначе каждый перезапуск сбрасывал бы демо-спортсменов и их рекомендации
        if args.if_empty and db.scalar(select(Athlete.id).limit(1)) is not None:
            print("Database already has athletes, demo data not created.")
            return

        # Удаляем прошлые демо-данные; тренировки, подходы и рекомендации
        # удалит сама база по ON DELETE CASCADE
        db.execute(delete(Athlete).where(Athlete.name.startswith(DEMO_PREFIX)))

        for name, strokes, goal, weeks_out, profile, seed in PROFILES:
            athlete = Athlete(
                name=f"{DEMO_PREFIX} {name}",
                main_strokes=strokes,
                goal_event=goal,
                goal_date=end + timedelta(weeks=weeks_out),
            )
            athlete.workouts = profile(random.Random(seed), end)
            db.add(athlete)
        db.commit()

        print(
            f"{'athlete':<14} {'id':>3} {'workouts':>8} {'vol 7d, m':>10} {'ACWR':>5}  zone"
        )
        for athlete in db.scalars(
            select(Athlete).where(Athlete.name.startswith(DEMO_PREFIX))
        ):
            s = summarize(athlete.workouts, end)
            print(
                f"{athlete.name:<14} {athlete.id:>3} {len(athlete.workouts):>8} "
                f"{s['volume_last_7d_m']:>10} {s['acwr']:>5}  {s['acwr_zone']}"
            )


if __name__ == "__main__":
    main()
