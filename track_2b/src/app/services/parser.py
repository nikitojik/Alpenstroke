import re

from app.models import Course
from app.schemas.parse import ParsedWorkout, ParseResponse, WorkoutExtraction
from app.services.llm import chat_json
from app.services.set_rules import (
    COOLDOWN_WORDS,
    WARMUP_WORDS,
    detect_course,
    fix_set,
    glossary_for_prompt,
    set_problems,
)

PARSE_SYSTEM = f"""You convert a swimmer's free-text workout log into structured data.

Rules:
- "10x100 free on 1:30" means reps=10, distance=100, stroke=freestyle, interval_s=90.
- "on 1:30" or "@1:30" is the send-off interval (interval_s). "15s rest" or ":15 rest" is rest (rest_s).
- Times like 1:30 are minutes:seconds. Always convert to seconds.
- A single swim without "x" (for example "400 warm up") is one set with reps=1.
- One continuous swim stays ONE set, even if the log says something happened during it.
  "3000 fly, shoulders started hurting in the second km" is one set: reps=1, distance=3000.
- Strokes, in any language (words may be beginnings of words):
{glossary_for_prompt()}
- Each set has its own stroke. Never copy a stroke from another set.
- A warm-up or cool-down that does not name a stroke is "choice", even when the next set names one.
  Warm-up words: {', '.join(WARMUP_WORDS)}.
  Cool-down words: {', '.join(COOLDOWN_WORDS)}.
- A main set that does not name a stroke is freestyle.
- The pool length is NOT a set. A bare 25 or 50 next to "pool", "m", "yards" or the time and effort
  describes the pool, for example "25 yard pool", "25 метров", "25-m-Becken", "Bassin de 25 m",
  "Vasca da 50". Never turn it into a set.
- course depends on the unit and the length of the pool:
  25 metres (m, метров, Meter, mètres, metri) or "short course meters" -> SCM;
  50 metres or "long course" (Langbahn) -> LCM; 25 yards (yd, ярдов) -> SCY.
  If the pool is not stated, course is null. Never guess it.
- perceived_effort is RPE from 1 to 10. A number always wins over a word: "на 10", "6 из 10",
  "felt like a 7", "RPE 6" give that number. Only if there is no number, map a clear description
  (easy ~3, moderate ~5, hard ~7, all-out ~9). Otherwise null.
- duration_min only if the swimmer states it. Otherwise null.
- symptoms: pain, cramps, injuries or illness the swimmer mentions, as short phrases
  ALWAYS IN ENGLISH, even when the log is in another language. Translate them,
  for example "болят плечи" -> "shoulder pain", "Wadenkrampf" -> "calf cramp".
- notes: anything else worth keeping (how it felt, technique), in the swimmer's own words.
- source: for every set, copy the words of the log this set comes from, unchanged and only
  for this set, for example "Разминка 400" or "10x100 free on 1:30".
- The log may be in any language. Never invent sets, numbers or symptoms that are not in the text."""

REQUIRED_TO_SAVE = ("course", "duration_min", "total_distance", "perceived_effort")

_NON_LATIN = re.compile(r"[^\x00-\x7F]")


def english_symptoms_check(parsed: WorkoutExtraction) -> list[str]:
    """Симптомы должны быть на английском: по ним работает проверка частей тела."""
    foreign = [s for s in parsed.symptoms if _NON_LATIN.search(s)]
    if not foreign:
        return []
    return [
        f"These symptoms are not in English: {foreign}. Translate every symptom to English."
    ]


def parse_workout_text(text: str, course_hint: Course | None = None) -> ParseResponse:
    def check(extracted: WorkoutExtraction) -> list[str]:
        return english_symptoms_check(extracted) + set_problems(text, extracted.sets)

    extracted, _raw = chat_json(
        PARSE_SYSTEM, text, WorkoutExtraction, temperature=0.1, check=check
    )
    parsed = ParsedWorkout(**extracted.model_dump())

    parsed.sets = [fix_set(s) for s in parsed.sets]
    parsed.course = course_hint or detect_course(text) or parsed.course

    if parsed.sets:
        parsed.total_distance = sum(s.distance * s.reps for s in parsed.sets)

    missing = [field for field in REQUIRED_TO_SAVE if getattr(parsed, field) is None]
    return ParseResponse(**parsed.model_dump(), missing=missing)
