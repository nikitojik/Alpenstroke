from app.models import Course
from app.schemas.parse import ParsedWorkout, ParseResponse
from app.services.llm import chat_json

PARSE_SYSTEM = """You convert a swimmer's free-text workout log into structured data.

Rules:
- "10x100 free on 1:30" means reps=10, distance=100, stroke=freestyle, interval_s=90.
- "on 1:30" or "@1:30" is the send-off interval (interval_s). "15s rest" or ":15 rest" is rest (rest_s).
- Times like 1:30 are minutes:seconds. Always convert to seconds.
- A single swim without "x" (for example "400 warm up") is one set with reps=1.
- Strokes: free/freestyle/FR -> freestyle; fly/butterfly -> fly; breast -> breaststroke;
  back -> backstroke; IM/medley -> medley. If no stroke is given, use freestyle.
- course: "yards", "yd", "SCY" -> SCY; "SCM", "25m" -> SCM; "LCM", "50m pool", "long course" -> LCM.
  If the pool is not stated, use null.
- perceived_effort is RPE from 1 to 10. Use it only if the swimmer states it or clearly
  describes effort (easy ~3, moderate ~5, hard ~7, all-out ~9). Otherwise null.
- duration_min only if the swimmer states it. Otherwise null.
- symptoms: pain, cramps, injuries or illness the swimmer mentions, as short English phrases.
- notes: anything else worth keeping (how it felt, technique), in the swimmer's own words.
- The log may be in any language. Never invent sets, numbers or symptoms that are not in the text."""

REQUIRED_TO_SAVE = ("course", "duration_min", "total_distance", "perceived_effort")


def parse_workout_text(text: str, course_hint: Course | None = None) -> ParseResponse:
    parsed, _raw = chat_json(PARSE_SYSTEM, text, ParsedWorkout, temperature=0.1)

    if course_hint is not None:
        parsed.course = course_hint

    if parsed.sets:
        parsed.total_distance = sum(s.distance * s.reps for s in parsed.sets)

    missing = [field for field in REQUIRED_TO_SAVE if getattr(parsed, field) is None]
    return ParseResponse(**parsed.model_dump(), missing=missing)