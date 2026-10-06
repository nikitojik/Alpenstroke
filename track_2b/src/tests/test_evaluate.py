"""Тесты подсчёта метрик eval-скрипта. Без сети и базы."""

from datetime import date

from scripts.evaluate import build_profile, score_analysis, score_parse

EXPECTED = {
    "course": "SCY",
    "duration_min": 90,
    "perceived_effort": 7,
    "total_distance": 1400,
    "sets": [
        {
            "stroke": "choice",
            "distance": 400,
            "reps": 1,
            "interval_s": None,
            "rest_s": None,
        },
        {
            "stroke": "freestyle",
            "distance": 100,
            "reps": 10,
            "interval_s": 90,
            "rest_s": None,
        },
    ],
    "symptoms": ["calf|calv"],
}


def parsed(**changes) -> dict:
    got = {**EXPECTED, "symptoms": ["calf cramp"]}
    return {**got, **changes}


def test_perfect_answer_scores_every_field():
    assert all(score_parse(EXPECTED, parsed()).values())


def test_set_order_does_not_matter():
    assert score_parse(EXPECTED, parsed(sets=EXPECTED["sets"][::-1]))["sets"]


def test_wrong_interval_fails_only_intervals():
    sets = [EXPECTED["sets"][0], {**EXPECTED["sets"][1], "interval_s": 100}]
    score = score_parse(EXPECTED, parsed(sets=sets))
    assert score["sets"] and not score["intervals"]


def test_untranslated_symptom_fails():
    assert not score_parse(EXPECTED, parsed(symptoms=["судорога в икре"]))["symptoms"]


def test_invented_symptom_fails_when_none_expected():
    expected = {**EXPECTED, "symptoms": []}
    assert not score_parse(expected, parsed(symptoms=["shoulder pain"]))["symptoms"]


def test_analysis_scoring():
    case = {"expected_concerns": ["symptom"], "forbidden_concerns": ["overload"]}
    good = {"concerns": [{"type": "symptom", "detail": "calf cramp"}]}
    bad = {"concerns": [{"type": "overload", "detail": "..."}]}
    assert all(score_analysis(case, good, []).values())
    score = score_analysis(case, bad, ["shoulder"])
    assert (
        not score["expected_found"]
        and not score["nothing_forbidden"]
        and not score["grounded"]
    )


def test_profiles_are_the_seed_athletes():
    athlete, history = build_profile("cramps", date(2026, 10, 6))
    assert athlete.goal_event == "100 fly" and len(history) == 36
    assert any(w.symptoms for w in history)
