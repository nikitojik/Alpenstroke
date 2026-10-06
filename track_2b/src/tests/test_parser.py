from fastapi.testclient import TestClient

from app.main import app as api
from app.models import Course, Stroke
from app.schemas.parse import ParsedWorkout
from app.schemas.parse import ExtractedSet as SetIn  # серия от модели, с полем source
from app.services import parser
from app.services.llm import LLMError


def fake_chat_json(monkeypatch, result: ParsedWorkout):
    monkeypatch.setattr(parser, "chat_json", lambda *args, **kwargs: (result, "raw"))


def test_total_distance_is_computed_by_code(monkeypatch):
    # Модель ошиблась в сумме: 2000 вместо 10*100 + 8*50 = 1400
    fake_chat_json(
        monkeypatch,
        ParsedWorkout(
            total_distance=2000,
            sets=[
                SetIn(stroke=Stroke.freestyle, distance=100, reps=10),
                SetIn(stroke=Stroke.fly, distance=50, reps=8),
            ],
        ),
    )
    result = parser.parse_workout_text("10x100 free, 8x50 fly")
    assert result.total_distance == 1400


def test_course_hint_overrides_model(monkeypatch):
    fake_chat_json(monkeypatch, ParsedWorkout(course=Course.SCM))
    result = parser.parse_workout_text("some workout", course_hint=Course.SCY)
    assert result.course == Course.SCY


def test_missing_lists_fields_needed_to_save(monkeypatch):
    fake_chat_json(
        monkeypatch,
        ParsedWorkout(
            course=Course.SCY,
            sets=[SetIn(stroke=Stroke.freestyle, distance=400)],
        ),
    )
    result = parser.parse_workout_text("400 warm up in yards")
    assert result.missing == ["duration_min", "perceived_effort"]


def test_endpoint_returns_draft(monkeypatch):
    fake_chat_json(
        monkeypatch,
        ParsedWorkout(
            course=Course.SCY,
            duration_min=90,
            perceived_effort=7,
            sets=[SetIn(stroke=Stroke.fly, distance=50, reps=8, interval_s=50)],
            symptoms=["calf cramp"],
        ),
    )
    r = TestClient(api).post(
        "/workouts/parse", json={"text": "8x50 fly on :50, calf cramp"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_distance"] == 400
    assert body["symptoms"] == ["calf cramp"]
    assert body["missing"] == []


def test_endpoint_returns_502_when_model_fails(monkeypatch):
    def broken(*args, **kwargs):
        raise LLMError("model returned invalid output twice")

    monkeypatch.setattr(parser, "chat_json", broken)
    r = TestClient(api).post("/workouts/parse", json={"text": "10x100 free"})
    assert r.status_code == 502


# ---------- симптомы на английском ----------

from app.services.parser import english_symptoms_check  # noqa: E402


def test_russian_symptom_is_rejected():
    problems = english_symptoms_check(ParsedWorkout(symptoms=["боли в плечах"]))
    assert len(problems) == 1 and "English" in problems[0]


def test_english_symptoms_pass():
    assert (
        english_symptoms_check(ParsedWorkout(symptoms=["shoulder pain", "calf cramp"]))
        == []
    )


# ---------- формат ответа модели ----------

from app.schemas.parse import WorkoutExtraction  # noqa: E402


def test_model_is_not_asked_for_total_distance():
    # сумму считает код; в схеме для модели этого поля нет
    assert "total_distance" not in WorkoutExtraction.model_json_schema()["properties"]


def test_notes_list_is_accepted():
    # так модель ответила в eval: "notes": [] ломало разбор дважды подряд
    assert WorkoutExtraction.model_validate_json('{"notes": []}').notes is None
    assert (
        WorkoutExtraction.model_validate_json('{"notes": ["felt", "good"]}').notes
        == "felt good"
    )


def test_total_is_computed_when_model_sends_none(monkeypatch):
    fake_chat_json(
        monkeypatch,
        WorkoutExtraction(
            sets=[
                SetIn(stroke=Stroke.choice, distance=400),
                SetIn(stroke=Stroke.fly, distance=3000),
            ]
        ),
    )
    assert parser.parse_workout_text("400 warm up, 3000 fly").total_distance == 3400
