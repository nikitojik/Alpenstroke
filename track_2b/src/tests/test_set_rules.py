import pytest

from app.models import Course, Stroke
from app.schemas.parse import ExtractedSet
from app.services.set_rules import detect_course, fix_set, set_problems, strokes_in


def make(
    source, stroke="freestyle", distance=100, reps=1, interval_s=None, rest_s=None
):
    return ExtractedSet(
        stroke=stroke,
        distance=distance,
        reps=reps,
        interval_s=interval_s,
        rest_s=rest_s,
        source=source,
    )


# ---------- бассейн ----------


@pytest.mark.parametrize(
    "text, course",
    [
        ("400 warm up ... 25 yard pool, 90 min", Course.SCY),
        ("Разминка 300 ... 25 ярдов, 60 минут", Course.SCY),
        ("... 25 метров, 60 минут", Course.SCM),
        ("... 25-m-Becken, 70 Minuten", Course.SCM),
        ("... Bassin de 25 m, 75 minutes", Course.SCM),
        ("... 50-метровый бассейн, 50 минут", Course.LCM),
        ("... 50-m-Bahn, 65 Minuten", Course.LCM),
        ("Langbahn, 1000 Kraul", Course.LCM),
        ("Vasca da 50. Riscaldamento 500", Course.LCM),
    ],
)
def test_pool_is_found_in_any_language(text, course):
    assert detect_course(text) == course


def test_minutes_and_sets_are_not_a_pool():
    # «50 минут» и «8x50 m» — не длина бассейна
    assert detect_course("8x50 m fly, 50 минут, 25 min") is None


def test_two_different_pools_give_no_answer():
    assert detect_course("25 m pool today, 50 m pool tomorrow") is None


# ---------- стиль по цитате ----------


def test_warm_up_without_stroke_becomes_choice():
    # так ошибалась модель: разминка получила стиль следующей серии
    assert (
        fix_set(make("Échauffement 300", stroke="breaststroke")).stroke == Stroke.choice
    )
    assert (
        fix_set(make("Riscaldamento 300", stroke="breaststroke")).stroke
        == Stroke.choice
    )


def test_stroke_named_in_source_wins():
    assert (
        fix_set(make("5 по 200 комплексом на 3:20", stroke="choice")).stroke
        == Stroke.medley
    )
    assert (
        fix_set(make("Разминка 800 кролем", stroke="choice")).stroke == Stroke.freestyle
    )


def test_short_words_need_whole_word():
    # «fr» не должно находиться во «french», «im» — в «swim»
    assert strokes_in("french swim drills") == set()


def test_two_strokes_in_source_leave_model_answer():
    s = fix_set(make("4x100 breast pull with back kick", stroke="breaststroke"))
    assert s.stroke == Stroke.breaststroke


def test_set_without_source_is_untouched():
    assert fix_set(make(None, stroke="fly")).stroke == Stroke.fly


# ---------- отдых и режим ----------


def test_rest_is_moved_from_interval():
    s = fix_set(
        make(
            "8 по 50 брассом с отдыхом 20 секунд", stroke="breaststroke", interval_s=20
        )
    )
    assert (s.interval_s, s.rest_s) == (None, 20)


def test_send_off_with_rest_stays():
    s = fix_set(make("10x100 free on 1:30 with 15s rest", interval_s=90, rest_s=15))
    assert (s.interval_s, s.rest_s) == (90, 15)


def test_lost_warm_up_is_reported():
    text = "Бассейн 50 м. Разминка 600. Основная: 10 по 100 вольным на 1:40."
    problems = set_problems(
        text, [make("10 по 100 вольным на 1:40", reps=10, interval_s=100)]
    )
    assert len(problems) == 1 and "warm-up" in problems[0]


def test_invented_distance_is_reported():
    # it-01: «300 stile libero» модель записала как 200
    problems = set_problems(
        "300 stile libero defaticamento",
        [make("300 stile libero defaticamento", distance=200)],
    )
    assert len(problems) == 1 and "200" in problems[0]


def test_correct_sets_have_no_problems():
    text = "Разминка 400, потом 3000 метров баттерфляем"
    sets = [
        make("Разминка 400", stroke="choice", distance=400),
        make("3000 метров баттерфляем", stroke="fly", distance=3000),
    ]
    assert set_problems(text, sets) == []


def test_same_source_for_two_sets_is_reported():
    sets = [
        make("4x200 Rücken auf 3:30", stroke="backstroke", distance=200, reps=4),
        make("4x200 Rücken auf 3:30", stroke="choice", distance=200),
    ]
    problems = set_problems("4x200 Rücken auf 3:30, 200 ausschwimmen", sets)
    assert any("same source" in p for p in problems)


# ---------- стиль в любом написании (так отвечает Apertus 8B) ----------


@pytest.mark.parametrize(
    "given, stroke",
    [
        ("butterfly", Stroke.fly),
        ("IM", Stroke.medley),
        ("free", Stroke.freestyle),
        ("Breaststroke", Stroke.breaststroke),
        ("back", Stroke.backstroke),
    ],
)
def test_any_spelling_of_a_stroke_is_accepted(given, stroke):
    assert ExtractedSet(stroke=given, distance=100).stroke == stroke


def test_unknown_or_missing_stroke_is_left_for_code():
    assert ExtractedSet(stroke="kick", distance=100).stroke is None
    assert ExtractedSet(distance=100).stroke is None


def test_code_fills_missing_stroke():
    assert (
        fix_set(make("Разминка 400", stroke=None, distance=400)).stroke == Stroke.choice
    )
    assert (
        fix_set(make("6 по 200 на 3:00", stroke=None, distance=200, reps=6)).stroke
        == Stroke.freestyle
    )
    assert fix_set(make("4x100 IM", stroke=None)).stroke == Stroke.medley
