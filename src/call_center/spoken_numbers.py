"""Spoken numbers in transcript text: number words read as digits.

A spoken run is a maximal sequence of number words and plain written digit groups that
holds at least one number word. It may cross a segment join. Two tokens of a run are
separated by whitespace; or by up to three punctuation marks (``,`` ``.`` ``;`` ``:`` ``-``
``–`` ``—`` ``(`` ``)``) with optional whitespace around each mark (so ``...``, `` - ``,
``—``, ``) (``, ``, -`` and ``five-five`` all qualify); or by a segment join, where the
join space may sit next to such a separator (a hyphen at the start or end of a segment
included). Finding the runs is linear in the length of the text and the number of joins.

Written digits that are not a plain digit group never join a run and end it like an
ordinary word: an amount (after a currency sign, or digits with a decimal point and 1-2
digits after it, ``19.99``), a time (``10:30``), a date (``2024-01-15``, ``1/15/2024``,
``01-15-2024``, ``15.01.2024``), and
digits glued to a letter on either side (``UA123``, ``A1B2C3``).

Number words (any case): ``zero``/``oh``/``o`` and ``one``-``nine`` are one digit;
``ten``-``nineteen`` are two; ``twenty``-``ninety`` are two (``twenty`` is ``20``,
``twenty five`` or ``twenty-five`` is ``25``); ``double``/``triple`` plus a digit word
repeats it (``55``, ``555``); ``hundred`` is ``00``, but only directly after (whitespace
only between) a digit word that itself follows another number word in the run (``one eight
hundred`` is ``1800``, while ``five hundred`` is not a run of digits). Homophones (``for``,
``to``, ``won``) are not number words. A segment join between a tens word and its unit
splits them (``twenty`` + ``five`` is ``20 5``); one between ``double``/``triple`` and its
digit word leaves the repeat word an ordinary word.

``digit_reading`` turns a run into its digits: whitespace between two number words adds
nothing; punctuation, a segment join, and whitespace next to a written digit group become
one group separator (a space). Each character of the reading maps back to the token that
produced it, and each is flagged as spoken (from a number word) or not. Every quantifier is
bounded.
"""

import re
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

UNITS: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
TEENS: dict[str, str] = {
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
}
TENS: dict[str, str] = {
    "twenty": "2",
    "thirty": "3",
    "forty": "4",
    "fifty": "5",
    "sixty": "6",
    "seventy": "7",
    "eighty": "8",
    "ninety": "9",
}
REPEATS: dict[str, int] = {"double": 2, "triple": 3}

# Punctuation that separates two tokens of a run (up to three marks).
SEPARATING_PUNCTUATION = frozenset(",.;:-–—()")
_MAX_MARKS = 3
# Whitespace between two marks of a separator, at most this many characters each.
_MAX_INNER_SPACE = 3
_MAX_CORE = _MAX_MARKS + (_MAX_MARKS - 1) * _MAX_INNER_SPACE

_UNIT = "|".join(UNITS)
_NONZERO_UNIT = "|".join(w for w, d in UNITS.items() if d != "0")
# A word token is not part of a longer word (letters, digits, underscore or apostrophe, so
# "o'clock" holds no "o").
_WB_BEFORE, _WB_AFTER = r"(?<![\w'])", r"(?![\w'])"
_WORD_PATTERN = (
    rf"{_WB_BEFORE}(?:"
    rf"(?P<tens>{'|'.join(TENS)})(?:(?:-|\s{{1,3}})(?P<tens_unit>{_NONZERO_UNIT}){_WB_AFTER})?"
    rf"|(?P<rep>{'|'.join(REPEATS)})\s{{1,3}}(?P<rep_unit>{_UNIT})"
    rf"|(?P<teen>{'|'.join(TEENS)})"
    r"|(?P<hundred>hundred)"
    rf"|(?P<unit>{_UNIT})"
    rf"){_WB_AFTER}"
)
# Written digits that are not a plain digit group: an amount after a currency sign, a
# time, or a date. Tried before a plain group, at the start of a digit stretch only.
_OTHER_PATTERN = (
    r"(?P<other>(?<![0-9])(?:"
    r"[$€£¥]\s?[0-9]{1,32}(?:,[0-9]{3}){0,8}(?:\.[0-9]{1,2})?"
    r"|[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?"
    r"|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}"
    r"|(?<![0-9][-.])[0-9]{1,2}[-.][0-9]{1,2}[-.][0-9]{2,4}(?![-.]?[0-9])"
    r"|[0-9]{1,4}/[0-9]{1,2}(?:/[0-9]{1,4})?"
    r")(?![0-9]))"
)
TOKEN = re.compile(
    # What a token can start with, so other positions are passed over quickly.
    r"(?=[0-9$€£¥+zotfsenhd])(?:"
    + _OTHER_PATTERN
    + "|"
    + _WORD_PATTERN
    # A written digit group: digits, optionally a leading "+" and inner "-" or "." between
    # digits. A longer stretch arrives as consecutive matches with nothing between them.
    + r"|(?P<written>\+?[0-9]{1,64}(?:[-.][0-9]{1,64}){0,16}))",
    re.IGNORECASE,
)
# Any number word at all: text without one has no runs, so it is not tokenized.
_ANY_WORD = re.compile(_WORD_PATTERN, re.IGNORECASE)
# A decimal point with 1-2 digits after it makes a written group an amount.
_DECIMAL = re.compile(r"\.[0-9]{1,2}(?![0-9])")

WORD, WRITTEN = "word", "written"
# Separator kinds before a token: nothing at all (consecutive written matches), whitespace,
# punctuation, or a segment join.
NONE, SPACE, PUNCT, JOIN = "", "space", "punct", "join"


class Token(NamedTuple):
    start: int
    end: int
    kind: str  # WORD or WRITTEN
    # A word's digits; for a written group, its text as written.
    digits: str
    # True for a single-digit word (zero/oh/o/one-nine), the only kind "hundred" may follow.
    unit: bool = False


@dataclass(frozen=True)
class Run:
    tokens: tuple[Token, ...]
    # seps[i] is the separator before tokens[i]; seps[0] is always NONE.
    seps: tuple[str, ...]

    @property
    def start(self) -> int:
        return self.tokens[0].start

    @property
    def end(self) -> int:
        return self.tokens[-1].end


class Reading(NamedTuple):
    """A run's digit reading. ``index_map[i]`` is the (start, end) in the original text of
    the token that produced ``view[i]``, or None for a group separator; ``joins`` are the
    offsets in ``view`` of separators that come from a segment join; ``spoken[i]`` is True
    when ``view[i]`` comes from a number word."""

    view: str
    index_map: list[tuple[int, int] | None]
    joins: list[int]
    spoken: list[bool]


def word_digits(word: str) -> str | None:
    """The digits of one number-word token (``"twenty-five"``, ``"double oh"``), or None."""
    m = TOKEN.fullmatch(word)
    if m is None or any(m.group(name) is not None for name in ("other", "written", "hundred")):
        return None
    return _tokens(m, ())[0][0].digits


def _tokens(m: re.Match[str], joins: Sequence[int]) -> list[tuple[Token, str | None]]:
    """The token(s) of word or written match ``m``, each with the separator kind before it
    inside the match (None for the first). A tens word whose unit lies across a segment
    join is two tokens, since the join separates them; a repeat word whose digit word lies
    across one is no number word, so only the digit word is a token."""
    start, end = m.span()
    name = m.lastgroup
    if name == "unit":
        return [(Token(start, end, WORD, UNITS[m.group().casefold()], True), None)]
    if name == "written":
        return [(Token(start, end, WRITTEN, m.group()), None)]
    if name == "teen":
        return [(Token(start, end, WORD, TEENS[m.group().casefold()]), None)]
    if name == "hundred":
        return [(Token(start, end, WORD, "00"), None)]
    if name in ("tens", "tens_unit"):
        tens = TENS[m.group("tens").casefold()]
        unit = m.group("tens_unit")
        if unit is None:
            return [(Token(start, end, WORD, tens + "0"), None)]
        if _has_join(joins, m.end("tens"), m.start("tens_unit")):
            return [
                (Token(start, m.end("tens"), WORD, tens + "0"), None),
                (Token(m.start("tens_unit"), end, WORD, UNITS[unit.casefold()], True), JOIN),
            ]
        return [(Token(start, end, WORD, tens + UNITS[unit.casefold()]), None)]
    # A repeat word and its digit word.
    unit = UNITS[m.group("rep_unit").casefold()]
    if _has_join(joins, m.end("rep"), m.start("rep_unit")):
        return [(Token(m.start("rep_unit"), end, WORD, unit, True), None)]
    return [(Token(start, end, WORD, unit * REPEATS[m.group("rep").casefold()]), None)]


def _has_join(joins: Sequence[int], lo: int, hi: int) -> bool:
    return bisect_left(joins, lo) < bisect_left(joins, hi)


def _punctuation_gap(gap: str) -> bool:
    """True for 1-3 separating marks, with optional whitespace around each mark."""
    core = gap.strip()
    if not 0 < len(core) <= _MAX_CORE:
        return False
    marks = "".join(core.split())
    if not (len(marks) <= _MAX_MARKS and all(ch in SEPARATING_PUNCTUATION for ch in marks)):
        return False
    return all(len(space) <= _MAX_INNER_SPACE for space in re.split(r"[^\s]", core))


def _glued(text: str, start: int, end: int) -> bool:
    """True when the written group ``text[start:end]`` touches a letter on either side."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return before.isalpha() or before == "_" or after.isalpha() or after == "_"


def separator(text: str, lo: int, hi: int, joins: Sequence[int] = ()) -> str | None:
    """The separator kind of ``text[lo:hi]`` between two tokens, or None when it is not a
    separator (it ends a run). ``joins`` are the sorted offsets of segment join spaces."""
    gap = text[lo:hi]
    k, k_end = bisect_left(joins, lo), bisect_left(joins, hi)
    if k < k_end:
        core = gap.strip()
        # Each join space removes at most one character, so a longer core cannot be a
        # separator; this also keeps the work below linear in the gap and its joins.
        if len(core) > _MAX_CORE + (k_end - k):
            return None
        offset = lo + len(gap) - len(gap.lstrip())
        cut = {p - offset for p in joins[k:k_end]}
        rest = "".join(ch for i, ch in enumerate(core) if i not in cut)
        return JOIN if (rest == "" or rest.isspace() or _punctuation_gap(rest)) else None
    if gap == "":
        return NONE
    if gap.isspace():
        return SPACE
    return PUNCT if _punctuation_gap(gap) else None


def find_runs(text: str, joins: Sequence[int] = ()) -> list[Run]:
    """Spoken runs in ``text``, in order. ``joins`` are the sorted offsets of the spaces
    that join segments."""
    runs: list[Run] = []
    if _ANY_WORD.search(text) is None:
        return runs
    tokens: list[Token] = []
    seps: list[str] = []

    def close() -> None:
        if any(t.kind == WORD for t in tokens):
            runs.append(Run(tuple(tokens), tuple(seps)))
        tokens.clear()
        seps.clear()

    def drop_written_stretch(start: int) -> None:
        # Earlier matches of the same unbroken written stretch belong to the token that
        # is not plain, so they leave the run with it.
        while tokens and tokens[-1].kind == WRITTEN and tokens[-1].end == start:
            start = tokens[-1].start
            tokens.pop()
            seps.pop()

    next_join = 0  # index of the first join at or after the end of the last token
    for m in TOKEN.finditer(text):
        name = m.lastgroup
        if name == "other" or (
            name == "written"
            and (_glued(text, *m.span()) or _DECIMAL.search(m.group()) is not None)
        ):
            # Written digits that are not a plain group end the run like an ordinary word.
            drop_written_stretch(m.start())
            close()
            continue
        for tok, inner in _tokens(m, joins):
            sep = inner
            if sep is None and tokens:
                lo = tokens[-1].end
                while next_join < len(joins) and joins[next_join] < lo:
                    next_join += 1
                no_join = next_join == len(joins) or joins[next_join] >= tok.start
                if no_join and tok.start == lo + 1 and text[lo] == " ":
                    sep = SPACE  # The common case, without slicing the gap.
                else:
                    sep = separator(text, lo, tok.start, joins)
            if name == "hundred":
                # "hundred" counts only directly after a digit word that follows another
                # number word; anywhere else it is an ordinary word and ends the run.
                if not (
                    sep == SPACE
                    and tokens[-1].unit
                    and len(tokens) >= 2
                    and tokens[-2].kind == WORD
                ):
                    close()
                    continue
            if sep is None:
                close()
            if not tokens:
                sep = NONE
            seps.append(sep)
            tokens.append(tok)
    close()
    return runs


def digit_reading(run: Run) -> Reading:
    """``run`` read as digits, with a map from each character back to its token."""
    view: list[str] = []
    index_map: list[tuple[int, int] | None] = []
    joins: list[int] = []
    spoken: list[bool] = []
    size = 0
    prev_kind = ""
    for tok, sep in zip(run.tokens, run.seps, strict=True):
        if sep == PUNCT or sep == JOIN or (sep == SPACE and WRITTEN in (prev_kind, tok.kind)):
            if sep == JOIN:
                joins.append(size)
            view.append(" ")
            index_map.append(None)
            spoken.append(False)
            size += 1
        n = len(tok.digits)
        view.append(tok.digits)
        index_map.extend([(tok.start, tok.end)] * n)
        spoken.extend([tok.kind == WORD] * n)
        size += n
        prev_kind = tok.kind
    return Reading("".join(view), index_map, joins, spoken)
