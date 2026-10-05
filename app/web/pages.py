import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import AIRecommendation, Athlete, Course, Kind, Workout
from app.schemas.workout import WorkoutCreate
from app.services.analyzer import HISTORY_DAYS, _set_line, analyze_workout
from app.services.llm import LLMError
from app.services.metrics import summarize
from app.services.parser import parse_workout_text
from app.services.planner import generate_plan
from app.services.workouts import save_workout

BASE_DIR = Path(__file__).resolve().parent.parent  # папка app/
templates = Jinja2Templates(directory=BASE_DIR / "templates")

ZONE_LABELS = {
    "low": "Light week",
    "optimal": "On track",
    "elevated": "Building fast",
    "spike": "Overload",
    "insufficient_history": "Needs four weeks of logs",
}
CONCERN_LABELS = {
    "overload": "Overload",
    "undertraining": "Light load",
    "symptom": "Symptom",
    "taper": "Taper",
    "other": "Note",
}
COURSE_LABELS = {"SCY": "25 yd pool", "SCM": "25 m pool", "LCM": "50 m pool"}
FIELD_LABELS = {
    "workout_date": "Date",
    "course": "Pool",
    "duration_min": "Minutes",
    "total_distance": "Distance",
    "perceived_effort": "Effort",
}

ROPE_MIN, ROPE_MAX = 0.4, 2.0  # края шкалы ACWR на дорожке


def rope_position(acwr: float) -> float:
    """Где поставить метку на дорожке, в процентах ширины."""
    share = (acwr - ROPE_MIN) / (ROPE_MAX - ROPE_MIN)
    return round(min(max(share, 0.0), 1.0) * 100, 1)


def km(metres: int) -> str:
    return f"{metres / 1000:.1f} km"


def unit(course) -> str:
    """Единица дистанции для бассейна: ярды для SCY, метры для остальных."""
    value = getattr(course, "value", course)
    return "yd" if value == "SCY" else "m"


def day_label(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%a %d %b")


# Функции, доступные прямо в шаблонах
templates.env.globals.update(
    rope_position=rope_position,
    zone_label=lambda zone: ZONE_LABELS.get(zone, zone),
    concern_label=lambda kind: CONCERN_LABELS.get(kind, kind),
    course_labels=COURSE_LABELS,
)
templates.env.filters.update(km=km, unit=unit, set_line=_set_line, day_label=day_label)

router = APIRouter(include_in_schema=False)  # страниц не будет в /docs


# ---------- вспомогательные запросы ----------


def _athlete_or_404(db: Session, athlete_id: int) -> Athlete:
    athlete = db.get(Athlete, athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="Athlete not found")
    return athlete


def _history(db: Session, athlete_id: int, today: date) -> list[Workout]:
    """Тренировки за 42 дня, свежие первыми, вместе с подходами."""
    return list(
        db.scalars(
            select(Workout)
            .where(
                Workout.athlete_id == athlete_id,
                Workout.workout_date > today - timedelta(days=HISTORY_DAYS),
                Workout.workout_date <= today,
            )
            .order_by(Workout.workout_date.desc(), Workout.id.desc())
            .options(selectinload(Workout.sets))
        ).all()
    )


def _latest(db: Session, athlete_id: int, kind: Kind) -> AIRecommendation | None:
    return db.scalars(
        select(AIRecommendation)
        .where(AIRecommendation.athlete_id == athlete_id, AIRecommendation.kind == kind)
        .order_by(AIRecommendation.created_at.desc())
        .limit(1)
    ).first()


def _error(request: Request, message: str) -> HTMLResponse:
    """
    Ошибка в виде кусочка HTML со статусом 200. HTMX по умолчанию не вставляет
    ответы с кодами 4xx и 5xx, а нам нужно показать сообщение на месте.
    """
    return templates.TemplateResponse(request, "_error.html", {"message": message})


# ---------- страницы ----------


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    rows = []
    for athlete in db.scalars(select(Athlete).order_by(Athlete.id)):
        rows.append(
            {
                "athlete": athlete,
                "metrics": summarize(_history(db, athlete.id, today), today),
                "days_to_goal": (
                    (athlete.goal_date - today).days if athlete.goal_date else None
                ),
            }
        )
    return templates.TemplateResponse(request, "home.html", {"rows": rows})


@router.get("/swimmers/{athlete_id}", response_class=HTMLResponse)
def swimmer(request: Request, athlete_id: int, db: Session = Depends(get_db)):
    athlete = _athlete_or_404(db, athlete_id)
    today = date.today()
    history = _history(db, athlete_id, today)
    return templates.TemplateResponse(
        request,
        "swimmer.html",
        {
            "athlete": athlete,
            "metrics": summarize(history, today),
            "days_to_goal": (
                (athlete.goal_date - today).days if athlete.goal_date else None
            ),
            "recent": history[:10],
            "analysis": _latest(db, athlete_id, Kind.analysis),
            "plan": _latest(db, athlete_id, Kind.plan),
        },
    )


# ---------- действия (возвращают кусочки HTML для HTMX) ----------


@router.post("/swimmers/{athlete_id}/parse", response_class=HTMLResponse)
def parse(
    request: Request,
    athlete_id: int,
    text: str = Form(...),
    course: str = Form(""),
    db: Session = Depends(get_db),
):
    _athlete_or_404(db, athlete_id)
    try:
        draft = parse_workout_text(text, Course(course) if course else None)
    except LLMError:
        return _error(
            request, "Apertus could not read this log. Try again, or shorten the text."
        )
    return templates.TemplateResponse(
        request,
        "_draft.html",
        {
            "athlete_id": athlete_id,
            "draft": draft,
            "missing_labels": [FIELD_LABELS[f].lower() for f in draft.missing],
            "sets_json": json.dumps([s.model_dump(mode="json") for s in draft.sets]),
            "symptoms_json": json.dumps(draft.symptoms),
            "notes": text,  # исходный текст сохраняем как заметку: анализ ищет в ней симптомы
            "today": date.today(),
        },
    )


@router.post("/swimmers/{athlete_id}/workouts")
def save(
    request: Request,
    athlete_id: int,
    workout_date: str = Form(...),
    course: str = Form(""),
    duration_min: str = Form(""),
    total_distance: str = Form(""),
    perceived_effort: str = Form(""),
    notes: str = Form(""),
    sets_json: str = Form("[]"),
    symptoms_json: str = Form("[]"),
    db: Session = Depends(get_db),
):
    _athlete_or_404(db, athlete_id)
    sets = json.loads(sets_json or "[]")
    if sets:  # дистанцию по подходам считает код, а не форма
        total_distance = str(sum(s["distance"] * s.get("reps", 1) for s in sets))

    try:
        payload = WorkoutCreate(
            athlete_id=athlete_id,
            workout_date=workout_date,
            course=course or None,
            duration_min=duration_min or None,
            total_distance=total_distance or None,
            perceived_effort=perceived_effort or None,
            notes=notes or None,
            symptoms=json.loads(symptoms_json or "[]"),
            sets=sets,
        )
    except ValidationError as e:
        fields = sorted(
            {
                FIELD_LABELS.get(str(err["loc"][0]), str(err["loc"][0]))
                for err in e.errors()
            }
        )
        return _error(request, f"Check these fields: {', '.join(fields)}.")

    save_workout(db, payload)
    # HX-Redirect: HTMX перезагрузит страницу, и новая тренировка появится в списке
    return Response(status_code=200, headers={"HX-Redirect": f"/swimmers/{athlete_id}"})


@router.post(
    "/swimmers/{athlete_id}/workouts/{workout_id}/analyze", response_class=HTMLResponse
)
def analyze(
    request: Request, athlete_id: int, workout_id: int, db: Session = Depends(get_db)
):
    workout = db.get(Workout, workout_id)
    if workout is None or workout.athlete_id != athlete_id:
        raise HTTPException(status_code=404, detail="Workout not found")
    try:
        rec = analyze_workout(db, workout)
    except LLMError:
        return _error(request, "Apertus did not answer in time. Press Analyze again.")
    return templates.TemplateResponse(request, "_analysis.html", {"rec": rec})


@router.post("/swimmers/{athlete_id}/plan", response_class=HTMLResponse)
def plan(request: Request, athlete_id: int, db: Session = Depends(get_db)):
    athlete = _athlete_or_404(db, athlete_id)
    try:
        rec = generate_plan(db, athlete)
    except LLMError:
        return _error(
            request, "Apertus could not build the plan. Press Plan next week again."
        )
    return templates.TemplateResponse(request, "_plan.html", {"rec": rec})


@router.post("/recommendations/{rec_id}/feedback", response_class=HTMLResponse)
def feedback(
    request: Request,
    rec_id: int,
    helpful: str = Form(...),
    db: Session = Depends(get_db),
):
    rec = db.get(AIRecommendation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.was_helpful = helpful == "yes"
    db.commit()
    return templates.TemplateResponse(request, "_feedback.html", {"rec": rec})
