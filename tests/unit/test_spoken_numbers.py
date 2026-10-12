import re
import time

import pytest

from call_center import spoken_numbers
from call_center.spoken_numbers import digit_reading, find_runs, separator, word_digits

UNBOUNDED = re.compile(r"(?<!\\)[*+](?![^\[]*\])|\{\d*,\}")


def _readings(text: str, joins=()) -> list[str]:
    return [digit_reading(run).view for run in find_runs(text, joins)]


def _joined(*texts: str) -> tuple[str, list[int]]:
    joins, pos = [], 0
    for t in texts[:-1]:
        pos += len(t)
        joins.append(pos)
        pos += 1
    return " ".join(texts), joins


@pytest.mark.parametrize(
    ("word", "digits"),
    [
        ("zero", "0"),
        ("oh", "0"),
        ("o", "0"),
        ("O", "0"),
        ("one", "1"),
        ("two", "2"),
        ("three", "3"),
        ("four", "4"),
        ("Five", "5"),
        ("six", "6"),
        ("seven", "7"),
        ("eight", "8"),
        ("NINE", "9"),
        ("ten", "10"),
        ("eleven", "11"),
        ("twelve", "12"),
        ("thirteen", "13"),
        ("fourteen", "14"),
        ("fifteen", "15"),
        ("sixteen", "16"),
        ("seventeen", "17"),
        ("eighteen", "18"),
        ("nineteen", "19"),
        ("twenty", "20"),
        ("thirty", "30"),
        ("forty", "40"),
        ("fifty", "50"),
        ("sixty", "60"),
        ("seventy", "70"),
        ("eighty", "80"),
        ("ninety", "90"),
        ("twenty five", "25"),
        ("twenty-five", "25"),
        ("Forty-Two", "42"),
        ("ninety  nine", "99"),
        ("double five", "55"),
        ("double oh", "00"),
        ("triple seven", "777"),
        ("Triple O", "000"),
    ],
)
def test_word_digits(word, digits):
    assert word_digits(word) == digits


@pytest.mark.parametrize(
    "word",
    ["for", "to", "too", "won", "ate", "hundred", "double", "twenty oh", "1", "ones", "10:30"],
)
def test_not_a_number_word(word):
    assert word_digits(word) is None


@pytest.mark.parametrize(
    ("text", "readings"),
    [
        ("one eight hundred five", ["18005"]),
        ("call one eight hundred", ["1800"]),
        ("eight hundred", ["8"]),
        ("five hundred dollars", ["5"]),
        ("twelve hundred", ["12"]),
        ("one twelve hundred", ["112"]),
        ("one eight, hundred", ["18"]),
        ("one eight hundred hundred", ["1800"]),
        ("1 eight hundred", ["1 8"]),
        ("one, eight hundred", ["1 800"]),
    ],
)
def test_hundred_only_after_a_digit_word_that_follows_a_number_word(text, readings):
    assert _readings(text) == readings


@pytest.mark.parametrize(
    ("text", "readings"),
    [
        ("one two three", ["123"]),
        ("one  two\tthree", ["123"]),
        ("one, two. three; four: five- six", ["1 2 3 4 5 6"]),
        ("one,two", ["1 2"]),
        ("one , two", ["1 2"]),
        ("one -- two", ["1 2"]),
        ("one... two", ["1 2"]),
        ("one - two", ["1 2"]),
        ("one — two", ["1 2"]),
        ("one–two", ["1 2"]),
        ("five-five-five", ["5 5 5"]),
        ("(five five five) one", ["555 1"]),
        ("(555) one two", ["555 12"]),
        ("five) (five", ["5 5"]),
        ("one .... two", ["1", "2"]),
        ("one , , two", ["1 2"]),
        ("(five five five) (one two)", ["555 12"]),
        ("five, - one", ["5 1"]),
        ("one , , , , two", ["1", "2"]),
        ("one and two", ["1", "2"]),
        ("one / two", ["1", "2"]),
        ("call 555 one two three 4567", ["555 123 4567"]),
        ("call 555-123 one", ["555-123 1"]),
        ("call 555.123 one", ["555.123 1"]),
        ("dial +1 eight", ["+1 8"]),
        ("double five five", ["555"]),
        ("twenty twenty four", ["2024"]),
        ("ten o clock", ["100"]),
        ("o'clock and one's", []),
        ("someone tone oneself", []),
        ("1234 5678", []),
        ("one\x00two", ["1", "2"]),
    ],
)
def test_runs_and_separators(text, readings):
    assert _readings(text) == readings


@pytest.mark.parametrize(
    ("text", "readings"),
    [
        # Amounts, times, dates and digits glued to letters end a run like a word.
        ("at 10:30 one two", ["12"]),
        ("one 10:30:15 two", ["1", "2"]),
        ("I paid 19.99 one two", ["12"]),
        ("one 5.5 two", ["1", "2"]),
        ("for $19.99, one", ["1"]),
        ("for $ 1,299 one", ["1"]),
        ("one €20 two", ["1", "2"]),
        ("one 2024-01-15", ["1"]),
        ("one 1/15/2024 two", ["1", "2"]),
        ("on 01-15-2024 one two", ["12"]),
        ("one 1-15-2024, two", ["1", "2"]),
        ("one 15.01.2024 two", ["1", "2"]),
        ("Flight UA123 one two", ["12"]),
        ("one A1B2C3 two", ["1", "2"]),
        ("one 123abc two", ["1", "2"]),
        ("one2 three", ["3"]),
        ("one x_12 two", ["1", "2"]),
        ("one " + "1" * 70 + "a two", ["1", "2"]),
        ("one " + "1" * 70 + ".99 two", ["1", "2"]),
        # Plain groups do join.
        ("one 555-1234 two", ["1 555-1234 2"]),
        ("one 110:30", ["1 110 30"]),
    ],
)
def test_written_digits_that_are_not_plain_groups_end_a_run(text, readings):
    assert _readings(text) == readings


def test_join_is_a_separator_and_is_reported():
    text, joins = _joined("is five five", "five one")
    [run] = find_runs(text, joins)
    reading = digit_reading(run)
    assert reading.view == "55 51"
    assert reading.joins == [2]
    assert digit_reading(find_runs(text)[0]).view == "5551"


@pytest.mark.parametrize(
    ("a", "b", "reading"),
    [
        ("five five", "-five one", "55 51"),
        ("five five-", "five one", "55 51"),
        ("five five,", "-five one", "55 51"),
        ("five five...", "five one", "55 51"),
        ("five five (", ") five one", "55 51"),
        ("twenty", "five", "20 5"),
        ("twenty-", "five", "20 5"),
    ],
)
def test_join_next_to_punctuation_is_one_separator(a, b, reading):
    text, joins = _joined(a, b)
    [run] = find_runs(text, joins)
    assert digit_reading(run).view == reading
    assert digit_reading(run).joins == [reading.index(" ")]


@pytest.mark.parametrize(
    ("texts", "readings"),
    [
        # A repeat word whose digit word lies across a join is an ordinary word.
        (("press double", "one five five"), ["155"]),
        (("double", "five five"), ["55"]),
        (("triple", "oh one"), ["01"]),
        (("one triple", "five"), ["1", "5"]),
        (("triple five", "one"), ["555 1"]),
    ],
)
def test_repeat_word_never_reaches_across_a_join(texts, readings):
    text, joins = _joined(*texts)
    assert _readings(text, joins) == readings


@pytest.mark.parametrize(
    ("gap", "kind"),
    [
        ("", spoken_numbers.NONE),
        (" ", spoken_numbers.SPACE),
        ("\n\t ", spoken_numbers.SPACE),
        (",", spoken_numbers.PUNCT),
        (" ... ", spoken_numbers.PUNCT),
        (" ;:- ", spoken_numbers.PUNCT),
        (") ", spoken_numbers.PUNCT),
        (" (", spoken_numbers.PUNCT),
        (" — ", spoken_numbers.PUNCT),
        (", ,", spoken_numbers.PUNCT),
        (") (", spoken_numbers.PUNCT),
        (", - ", spoken_numbers.PUNCT),
        (" . . . ", spoken_numbers.PUNCT),
        ("....", None),
        (", , , ,", None),
        (",    ,", None),
        ("!", None),
        ("/", None),
        (" x ", None),
    ],
)
def test_separator_kinds(gap, kind):
    text = f"a{gap}b"
    assert separator(text, 1, 1 + len(gap)) == kind


def test_join_scanning_is_linear_in_segments():
    text, joins = _joined("one", *["hello there friend"] * 3000, "two")
    start = time.perf_counter()
    assert _readings(text, joins) == ["1", "2"]
    assert separator(" " * 5000, 0, 5000, list(range(5000))) == spoken_numbers.JOIN
    assert time.perf_counter() - start < 0.1


def test_index_map_and_spoken_flags_point_at_the_tokens():
    text = "x twelve, 4-5 six"
    [run] = find_runs(text)
    reading = digit_reading(run)
    assert reading.view == "12 4-5 6"
    twelve, written, six = (2, 8), (10, 13), (14, 17)
    assert reading.index_map == [twelve, twelve, None, written, written, written, None, six]
    assert reading.spoken == [True, True, False, False, False, False, False, True]
    assert run.start == 2 and run.end == 17


def test_long_written_digit_stretch_stays_in_one_run():
    text = "one " + "7" * 200
    [run] = find_runs(text)
    assert digit_reading(run).view == "1 " + "7" * 200
    assert run.end == len(text)


def test_patterns_are_bounded():
    for pattern in (spoken_numbers.TOKEN, spoken_numbers._ANY_WORD, spoken_numbers._DECIMAL):
        assert not UNBOUNDED.search(pattern.pattern)
