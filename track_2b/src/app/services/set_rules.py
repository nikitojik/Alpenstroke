import re

from app.models import Course, Stroke

STROKE_WORDS: dict[Stroke, list[str]] = {
    Stroke.freestyle: [
        "free",
        "freestyle",
        "crawl",
        "kraul",
        "вольн",
        "крол",
        "stile libero",
    ],
    Stroke.fly: [
        "fly",
        "butterfly",
        "delfin",
        "schmetterling",
        "papillon",
        "баттерфля",
        "дельфин",
        "farfalla",
    ],
    Stroke.breaststroke: ["breast", "brust", "brasse", "брасс", "rana"],
    Stroke.backstroke: ["back", "rücken", "на спин", "dorso"],
    Stroke.medley: ["medley", "lagen", "4 nages", "комплекс", "misti"],
    Stroke.choice: ["choice", "any stroke"],
}
EXACT_STROKE_WORDS: dict[Stroke, list[str]] = {
    Stroke.freestyle: ["fr"],
    Stroke.backstroke: ["dos"],
    Stroke.medley: ["im"],
}

WARMUP_WORDS = [
    "warm up",
    "warm-up",
    "warmup",
    "разминк",
    "einschwimm",
    "échauffement",
    "riscaldament",
]
COOLDOWN_WORDS = [
    "cool down",
    "cool-down",
    "cooldown",
    "заминк",
    "locker aus",
    "souple",
    "defaticament",
]

REST_WORDS = ["rest", "отдых", "pause", "récup", "recup", "riposo"]
SEND_OFF = re.compile(
    r"(?<!\w)(on|@|auf|départ|depart|partenza|на)\s*:?\d", re.IGNORECASE
)

_UNITS_M = r"(?:m|м|meter\w*|metre\w*|mètre\w*|metri|метр\w*)"
_UNITS_YD = r"(?:y|yd|yds|yard\w*|ярд\w*)"
COURSE_PATTERNS: list[tuple[Course, re.Pattern]] = [
    (
        Course.SCY,
        re.compile(
            rf"(?<![\dx×])\b25\s*-?\s*{_UNITS_YD}(?!\w)|short course yards|\bscy\b",
            re.I,
        ),
    ),
    (
        Course.SCM,
        re.compile(
            rf"(?<![\dx×])\b25\s*-?\s*{_UNITS_M}(?!\w)|short course met|vasca da 25\b|\bscm\b",
            re.I,
        ),
    ),
    (
        Course.LCM,
        re.compile(
            rf"(?<![\dx×])\b50\s*-?\s*{_UNITS_M}(?!\w)|long course|langbahn|vasca da 50\b|\blcm\b",
            re.I,
        ),
    ),
]


def _word_pattern(word: str, exact: bool) -> re.Pattern:
    return re.compile(
        rf"(?<!\w){re.escape(word)}" + (r"(?!\w)" if exact else ""), re.IGNORECASE
    )


_STROKE_PATTERNS = [
    (stroke, _word_pattern(w, exact))
    for table, exact in ((STROKE_WORDS, False), (EXACT_STROKE_WORDS, True))
    for stroke, words in table.items()
    for w in words
]


def _has(words: list[str], text: str) -> bool:
    return any(_word_pattern(w, exact=False).search(text) for w in words)


def strokes_in(fragment: str) -> set[Stroke]:
    """Какие стили названы в куске текста."""
    return {stroke for stroke, pattern in _STROKE_PATTERNS if pattern.search(fragment)}


def detect_course(text: str) -> Course | None:
    """Бассейн по явной записи в тексте. None, если записи нет или их несколько разных."""
    found = {course for course, pattern in COURSE_PATTERNS if pattern.search(text)}
    return found.pop() if len(found) == 1 else None


def fix_set(s):
    if s.source:
        named = strokes_in(s.source)
        if len(named) == 1:
            s.stroke = (
                named.pop()
            )
        elif not named and _has(WARMUP_WORDS + COOLDOWN_WORDS, s.source):
            s.stroke = Stroke.choice  # разминка или заминка без стиля
        if (
            s.interval_s
            and s.rest_s is None
            and _has(REST_WORDS, s.source)
            and not SEND_OFF.search(s.source)
        ):
            s.rest_s, s.interval_s = s.interval_s, None
    if s.stroke is None:
        warm_or_cool = bool(s.source) and _has(WARMUP_WORDS + COOLDOWN_WORDS, s.source)
        s.stroke = Stroke.choice if warm_or_cool else Stroke.freestyle
    return s


def set_problems(text: str, sets) -> list[str]:
    problems = []
    for i, s in enumerate(sets, start=1):
        if not s.source:
            problems.append(
                f"Set {i} has no 'source'. Copy the words of the log this set comes from."
            )
            continue
        numbers = {int(n) for n in re.findall(r"\d+", s.source)}
        if s.distance not in numbers:
            problems.append(
                f"Set {i}: distance {s.distance} does not appear in its source '{s.source}'. "
                f"Use only numbers written in the log."
            )
        if s.reps > 1 and s.reps not in numbers:
            problems.append(
                f"Set {i}: reps {s.reps} does not appear in its source '{s.source}'."
            )
    seen: dict[str, int] = {}
    for i, s in enumerate(sets, start=1):
        if s.source and s.source in seen:
            problems.append(
                f"Sets {seen[s.source]} and {i} have the same source '{s.source}'. "
                f"Each set must quote its own words."
            )
        seen.setdefault(s.source, i)
    sources = " ".join(s.source or "" for s in sets)
    for kind, words in (("warm-up", WARMUP_WORDS), ("cool-down", COOLDOWN_WORDS)):
        for w in words:
            if _has([w], text) and not _has([w], sources):
                problems.append(
                    f"The log has a {kind} ('{w}') but no set comes from it. Add it as a set."
                )
                break
    return problems


def glossary_for_prompt() -> str:
    lines = []
    for stroke in STROKE_WORDS:
        words = EXACT_STROKE_WORDS.get(stroke, []) + STROKE_WORDS[stroke]
        lines.append(f"  {stroke.value}: {', '.join(words)}")
    return "\n".join(lines)
