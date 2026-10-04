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


def _mentioned(text: str) -> set[str]:
    """Какие части тела встречаются в тексте. \\b — граница слова: 'hip' не найдётся в 'ship'."""
    text = text.lower()
    return {
        part
        for part, forms in BODY_PARTS.items()
        if any(re.search(rf"\b{re.escape(form)}\b", text) for form in forms)
    }


def ungrounded_body_parts(output: BaseModel, source_notes: list[str | None]) -> list[str]:
    """Части тела, которые модель упомянула, а в заметках их нет."""
    in_output = _mentioned(output.model_dump_json())
    in_notes = _mentioned(" ".join(n for n in source_notes if n))
    return sorted(in_output - in_notes)


def body_part_check(source_notes: list[str | None]):
    """
    Готовая функция-проверка для chat_json: возвращает список описаний ошибок
    (пустой, если всё в порядке).
    """
    def check(output: BaseModel) -> list[str]:
        return [
            f"You mentioned '{part}', but none of the swimmer's notes mention it. "
            f"Remove it and refer only to what the notes say."
            for part in ungrounded_body_parts(output, source_notes)
        ]
    return check