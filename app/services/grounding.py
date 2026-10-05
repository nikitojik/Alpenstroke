import re

from pydantic import BaseModel

BODY_PARTS = {
    "shoulder": ["shoulder", "shoulders"],
    "neck": ["neck"],
    "lower back": ["lower back"],
    "knee": ["knee", "knees"],
    "elbow": ["elbow", "elbows"],
    "hip": ["hip", "hips"],
    "wrist": ["wrist", "wrists"],
    "ankle": ["ankle", "ankles"],
    "calf": ["calf", "calves"],
    "hamstring": ["hamstring", "hamstrings"],
    "groin": ["groin"],
}

CONCERN_WORDS = (
    "pain",
    "painful",
    "sore",
    "ache",
    "aching",
    "hurt",
    "injur",
    "strain",
    "stress",
    "fatigue",
    "tired",
    "discomfort",
    "tight",
    "cramp",
    "protect",
    "overload",
    "irritat",
    "inflam",
    "tendin",
    "niggle",
    "issue",
    "problem",
)
CONTEXT_CHARS = 40  # сколько символов вокруг слова смотрим в поисках CONCERN_WORDS


def _pattern(form: str) -> re.Pattern:
    """\\b — граница слова: 'hip' не найдётся в 'ship', 'back' — в 'backstroke'."""
    return re.compile(rf"\b{re.escape(form)}\b")


def _mentioned(text: str) -> set[str]:
    """Какие части тела вообще встречаются в тексте (для заметок и симптомов)."""
    text = text.lower()
    return {
        part
        for part, forms in BODY_PARTS.items()
        if any(_pattern(form).search(text) for form in forms)
    }


def _mentioned_as_concern(text: str) -> set[str]:
    """Части тела, рядом с которыми есть слово про проблему (для ответа модели)."""
    text = text.lower()
    found = set()
    for part, forms in BODY_PARTS.items():
        for form in forms:
            for match in _pattern(form).finditer(text):
                window = text[
                    max(0, match.start() - CONTEXT_CHARS) : match.end() + CONTEXT_CHARS
                ]
                if any(word in window for word in CONCERN_WORDS):
                    found.add(part)
    return found


def grounding_sources(workouts) -> list[str | None]:
    """
    С чем сверять ответ модели: заметки (на языке спортсмена) и симптомы
    (на английском). Благодаря симптомам проверка работает для любого языка:
    «болят плечи» в заметке плюс "shoulder pain" в симптомах.
    """
    return [w.notes for w in workouts] + [" ".join(w.symptoms or []) for w in workouts]


def ungrounded_body_parts(
    output: BaseModel, source_notes: list[str | None]
) -> list[str]:
    """Части тела, которые модель упомянула как проблему, а в данных спортсмена их нет."""
    in_output = _mentioned_as_concern(output.model_dump_json())
    in_notes = _mentioned(" ".join(n for n in source_notes if n))
    return sorted(in_output - in_notes)


def body_part_check(source_notes: list[str | None]):
    """
    Готовая функция-проверка для chat_json: возвращает список описаний ошибок
    (пустой, если всё в порядке).
    """

    def check(output: BaseModel) -> list[str]:
        return [
            f"You mentioned a problem with '{part}', but none of the swimmer's notes mention it. "
            f"Remove it and refer only to what the notes say."
            for part in ungrounded_body_parts(output, source_notes)
        ]

    return check
