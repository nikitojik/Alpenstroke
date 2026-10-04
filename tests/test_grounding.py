"""Тесты проверки по источнику и её связки с chat_json. Без сети."""

from pydantic import BaseModel

from app.services import llm
from app.services.grounding import body_part_check, ungrounded_body_parts


class Advice(BaseModel):
    text: str


NOTES = ["calf cramp on the fly set", None, "left calf cramped again"]


def test_invented_shoulder_is_caught():
    out = Advice(text="Reduce fly to protect the shoulders and stretch the calves.")
    assert ungrounded_body_parts(out, NOTES) == ["shoulder"]


def test_grounded_body_part_is_allowed():
    # «calves» и «calf» — одна часть тела, и она есть в заметках
    assert ungrounded_body_parts(Advice(text="Stretch your calves."), NOTES) == []


def test_word_boundaries_avoid_false_matches():
    # 'hip' внутри 'relationship', 'back' внутри 'backstroke' — не части тела
    out = Advice(text="Good relationship with the water; add backstroke.")
    assert ungrounded_body_parts(out, NOTES) == []


def test_check_returns_readable_problem():
    problems = body_part_check(NOTES)(Advice(text="watch your neck"))
    assert len(problems) == 1 and "'neck'" in problems[0]


def fake_model(monkeypatch, *answers):
    queue, calls = list(answers), []

    def fake_complete(messages, temperature):
        calls.append(list(messages))
        return queue.pop(0)

    monkeypatch.setattr(llm, "_complete", fake_complete)
    return calls


def test_chat_json_retries_when_check_fails(monkeypatch):
    calls = fake_model(
        monkeypatch,
        '{"text": "protect your shoulders"}',  # выдуманная часть тела
        '{"text": "replace fly with freestyle"}',
    )
    obj, _ = llm.chat_json("sys", "user", Advice, check=body_part_check(NOTES))
    assert obj.text == "replace fly with freestyle"
    assert len(calls) == 2
    assert "'shoulder'" in calls[1][-1]["content"]


def test_chat_json_returns_second_answer_even_if_check_still_fails(monkeypatch):
    fake_model(monkeypatch, '{"text": "shoulders"}', '{"text": "shoulders again"}')
    obj, _ = llm.chat_json("sys", "user", Advice, check=body_part_check(NOTES))
    # формат верный, поэтому ответ возвращается; проблему запишут в grounding_warnings
    assert ungrounded_body_parts(obj, NOTES) == ["shoulder"]