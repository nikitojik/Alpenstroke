from typing import Literal

import pytest
from pydantic import BaseModel

from app.services import llm


class Verdict(BaseModel):
    summary: str
    confidence: Literal["low", "medium", "high"]


def fake_model(monkeypatch, *answers: str) -> list[list[dict]]:
    """Подменяет _complete: отдаёт ответы по очереди и запоминает запросы."""
    queue = list(answers)
    calls: list[list[dict]] = []

    def fake_complete(messages, temperature):
        calls.append(list(messages))
        return queue.pop(0)

    monkeypatch.setattr(llm, "_complete", fake_complete)
    return calls


def test_valid_json_first_try(monkeypatch):
    calls = fake_model(monkeypatch, '{"summary": "ok", "confidence": "high"}')
    obj, raw = llm.chat_json("sys", "user", Verdict)
    assert obj == Verdict(summary="ok", confidence="high")
    assert len(calls) == 1


def test_strips_code_fence_and_chatter(monkeypatch):
    fake_model(monkeypatch, 'Sure! Here it is:\n```json\n{"summary": "ok", "confidence": "low"}\n```')
    obj, _ = llm.chat_json("sys", "user", Verdict)
    assert obj.confidence == "low"


def test_retries_once_with_error_feedback(monkeypatch):
    calls = fake_model(
        monkeypatch,
        '{"summary": "ok", "confidence": "very high"}',  # неверное значение
        '{"summary": "ok", "confidence": "high"}',       # исправленный ответ
    )
    obj, raw = llm.chat_json("sys", "user", Verdict)
    assert obj.confidence == "high"
    assert len(calls) == 2
    # Во втором запросе модель видит свой ответ и описание ошибки
    assert calls[1][-2]["role"] == "assistant"
    assert "confidence" in calls[1][-1]["content"]


def test_gives_up_after_second_failure(monkeypatch):
    fake_model(monkeypatch, "not json", "still not json")
    with pytest.raises(llm.LLMError):
        llm.chat_json("sys", "user", Verdict)


def test_schema_is_added_to_system_prompt(monkeypatch):
    calls = fake_model(monkeypatch, '{"summary": "ok", "confidence": "high"}')
    llm.chat_json("You are a coach.", "user", Verdict)
    system = calls[0][0]["content"]
    assert system.startswith("You are a coach.")
    assert '"confidence"' in system and '"medium"' in system