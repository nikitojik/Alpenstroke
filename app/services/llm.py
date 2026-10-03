import json
from typing import TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Модель недоступна или дважды вернула ответ, не прошедший проверку."""


client = OpenAI(
    base_url=settings.apertus_base_url,
    api_key=settings.apertus_api_key,
    timeout=60,
)


def _complete(messages: list[dict], temperature: float) -> str:
    """Один запрос к модели. Ошибки сети и API превращаются в LLMError."""
    try:
        response = client.chat.completions.create(
            model=settings.apertus_model,
            messages=messages,
            temperature=temperature,
            max_tokens=1500,
        )
    except OpenAIError as e:
        raise LLMError(f"model request failed: {e}") from e
    return response.choices[0].message.content or ""


def _extract_json(text: str) -> str:
    """
    Достаёт JSON-объект из ответа. Модели любят оборачивать ответ
    в ```json ... ``` или добавлять фразу перед ним, поэтому берём
    всё от первой '{' до последней '}'.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start : end + 1]


def _schema_instructions(schema: type[BaseModel]) -> str:
    """Текст для системного промпта: JSON Schema, сгенерированная из Pydantic."""
    return (
        "\n\nReply with ONLY a JSON object, no other text. "
        "It must match this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


def chat_json(system: str, user: str, schema: type[T], temperature: float = 0.3) -> tuple[T, str]:
    """
    Отправляет промпт и возвращает (проверенный объект, сырой ответ модели).
    Сырой ответ сохраняем в базу (raw_response), чтобы потом разбирать ошибки.
    """
    messages = [
        {"role": "system", "content": system + _schema_instructions(schema)},
        {"role": "user", "content": user},
    ]

    raw = _complete(messages, temperature)
    try:
        return schema.model_validate_json(_extract_json(raw)), raw
    except ValidationError as error:
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "Your previous answer did not match the required schema. "
                    f"Errors: {error.errors(include_url=False)}. "
                    "Reply with ONLY the corrected JSON object."
                ),
            },
        ]

    raw = _complete(messages, temperature=0.0)
    try:
        return schema.model_validate_json(_extract_json(raw)), raw
    except ValidationError as error:
        raise LLMError("model returned invalid output twice") from error