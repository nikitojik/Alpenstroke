import json
from collections.abc import Callable
from typing import TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)


MAX_TOKENS = 3000


class LLMError(Exception):
    """Модель недоступна или дважды вернула ответ, не прошедший проверку."""


client = OpenAI(
    base_url=settings.apertus_base_url,
    api_key=settings.apertus_api_key,
    timeout=60,
)


def _complete(messages: list[dict], temperature: float) -> str:
    try:
        response = client.chat.completions.create(
            model=settings.apertus_model,
            messages=messages,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
        )
    except OpenAIError as e:
        raise LLMError(f"model request failed: {e}") from e
    return response.choices[0].message.content or ""


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return text
    return text[start : end + 1]


def _schema_instructions(schema: type[BaseModel]) -> str:
    return (
        "\n\nReply with ONLY a JSON object, no other text. "
        "It must match this JSON Schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


def _parse(
    raw: str, schema: type[T], check: Callable[[T], list[str]] | None
) -> tuple[T | None, list[str]]:
    """Разбор и проверки. Возвращает (объект или None, список проблем)."""
    try:
        obj = schema.model_validate_json(_extract_json(raw))
    except ValidationError as error:
        return None, [f"Invalid JSON for the schema: {error.errors(include_url=False)}"]
    problems = check(obj) if check else []
    return obj, problems


def chat_json(
    system: str,
    user: str,
    schema: type[T],
    temperature: float = 0.3,
    check: Callable[[T], list[str]] | None = None,
) -> tuple[T, str]:
    messages = [
        {"role": "system", "content": system + _schema_instructions(schema)},
        {"role": "user", "content": user},
    ]

    raw = _complete(messages, temperature)
    obj, problems = _parse(raw, schema, check)
    if obj is not None and not problems:
        return obj, raw

    messages += [
        {"role": "assistant", "content": raw},
        {
            "role": "user",
            "content": (
                "Your previous answer has problems:\n- "
                + "\n- ".join(problems)
                + "\nReply with ONLY the corrected JSON object."
            ),
        },
    ]
    raw = _complete(messages, temperature=0.0)
    obj, problems = _parse(raw, schema, check)
    if obj is None:
        reason = problems[0][:300] if problems else "unknown"
        ending = raw[-80:].replace("\n", " ")
        raise LLMError(
            f"model returned invalid output twice. Reason: {reason}. Answer ends with: ...{ending}"
        )
    return obj, raw
