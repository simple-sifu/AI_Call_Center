"""PII detection and redaction for transcript text.

Finds SSNs, payment card numbers (Luhn-checked), email addresses (written and spoken) and
North American phone numbers written as digits, and replaces each with ``[SSN]``,
``[CARD]``, ``[EMAIL]`` or ``[PHONE]``. Every other character is left byte-identical.

Emails (written, then spoken) are found first, so digits inside an address cannot break it
up. Then SSN and phone candidates are found. Then each run of digit groups joined by single
spaces or hyphens is examined for cards: a 13-19 digit window that starts and ends on a
group boundary, passes Luhn and overlaps no SSN/phone candidate. Card-shaped windows
(``4-4-4-4``, ``4-6-5``, ``4-4-4-4-3`` or one unbroken group) are preferred, then 16 digits,
then 15, then leftmost; the best is taken and the rest of the run is searched again, so a
stray group or CVV beside a card does not join it. When an equally good window overlaps a
chosen one and covers digits nothing else claimed (a 4-digit group beside a 4-4-4-4 card
can make both readings valid), the text cannot say which is the card, so their union is
redacted, erring toward privacy. A run with no card that is shaped like one number (13-19
unbroken digits, or card-style groups) is protected, so a 16-digit reference number is
never half-redacted as phones. The SSN/phone candidates then claim what cards and protected
runs left. Each pass runs on a working copy where claimed spans are masked out, so offsets
stay aligned with the original text. Every quantifier is bounded.

Text from several segments is joined with a space, and the join space is always kept. At a
join only, a hyphen next to the join space (``123-45-`` + ``6789`` or ``123-45`` +
``-6789``) also counts as one separator: the working copy holds the hyphen then a marker
in place of the two characters; this only adds matches,
since the marker still ends a digit run like a space does. A phone's ``1``/``+1`` prefix is
never taken from an earlier segment.
"""

import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence

SSN = "SSN"
CARD = "CARD"
EMAIL = "EMAIL"
PHONE = "PHONE"
TYPES: tuple[str, ...] = (SSN, CARD, EMAIL, PHONE)

# Stands in for a claimed or protected character in the working copy: not a digit, letter,
# separator or email character, so no later pattern matches it or treats it as one.
_MASK = "\x00"
# Stands in for a join space that follows ``digit-`` and precedes a digit. Patterns accept
# it right after a separating hyphen; everywhere else it is not a digit, so it ends a digit
# run exactly as the space it replaces would.
_JOIN = "\x01"
_ASCII_DIGITS = frozenset("0123456789")

# A digit match never starts or ends inside a longer digit run (digits, possibly joined by
# a hyphen or dot).
_LB = r"(?<!\d)(?<!\d[-.])"
_RB = r"(?![-.]?\d)"
# A hyphen between groups, optionally followed by a marked join space.
_H = "-\x01?"

# One group of a card candidate run; longer digit stretches arrive as consecutive matches
# and are merged back into one group.
_DIGIT_GROUP = re.compile(r"[0-9]{1,64}")
# What may join two groups of a card candidate run.
_GROUP_SEPARATORS = frozenset({" ", "-", "-" + _JOIN})
_CARD_MIN, _CARD_MAX = 13, 19
# Runs shaped like one number, by group lengths: 13-19 unbroken digits; four groups of four
# with an optional final group of 1-3; or 4-6-5.
_ONE_NUMBER_SHAPE = re.compile(r"1[3-9]|4,4,4,4(?:,[1-3])?|4,6,5")
# Card-shaped windows, by group lengths: one unbroken group, 4-4-4-4, 4-4-4-4-3 or 4-6-5.
_CARD_SHAPE = re.compile(r"1[3-9]|4,4,4,4(?:,3)?|4,6,5")

# A bare 9-digit number counts as an SSN, erring toward privacy.
_SSN = re.compile(rf"{_LB}(?:\d{{3}}{_H}\d{{2}}{_H}\d{{4}}|\d{{3}} \d{{2}} \d{{4}}|\d{{9}}){_RB}")

_PHONE = re.compile(
    rf"{_LB}(?P<prefix>\+?1[ .-]?)?"
    rf"(?:\(\d{{3}}\) ?\d{{3}}{_H}\d{{4}}|\d{{3}}{_H}\d{{3}}{_H}\d{{4}}|\d{{3}}\.\d{{3}}\.\d{{4}}"
    rf"|\d{{3}} \d{{3}} \d{{4}}|\d{{10}}){_RB}"
    rf"|{_LB}\d{{3}}{_H}\d{{4}}{_RB}"
)

_LOCAL_CHARS = r"A-Za-z0-9._%+-"
_EMAIL = re.compile(
    rf"(?<![{_LOCAL_CHARS}])[{_LOCAL_CHARS}]{{1,64}}"
    r"@(?:[A-Za-z0-9-]{1,63}\.){1,8}[A-Za-z]{2,24}(?![A-Za-z0-9-])"
)

_SPOKEN_TLDS = r"(?:com|net|org|edu|gov|io|co|us|uk|ca)"
_SPOKEN_EMAIL = re.compile(
    rf"(?<![{_LOCAL_CHARS}])[{_LOCAL_CHARS}]{{1,64}}\s{{1,3}}at\s{{1,3}}"
    rf"(?:[A-Za-z0-9-]{{1,63}}\s{{1,3}}dot\s{{1,3}}){{1,4}}{_SPOKEN_TLDS}(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Passes before the digit passes, in order.
_EMAIL_PASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (EMAIL, _EMAIL),
    (EMAIL, _SPOKEN_EMAIL),
)
_DIGIT_PASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (SSN, _SSN),
    (PHONE, _PHONE),
)

# (start, end, type) in the joined text.
_Span = tuple[int, int, str]


def luhn_valid(digits: str) -> bool:
    """True when ``digits`` (digits only) passes the Luhn checksum."""
    if not (digits.isascii() and digits.isdigit()):
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _mask(text: str, spans: Sequence[tuple[int, int]]) -> str:
    parts, pos = [], 0
    for start, end in sorted(spans):
        parts.append(text[pos:start])
        parts.append(_MASK * (end - start))
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def _mark_joins(text: str, joins: Sequence[int]) -> str:
    """``text`` with each join between digits that has a hyphen on either side of the join
    space (``5- 6`` or ``5 -6``) rewritten as a hyphen then ``_JOIN`` (same length, so
    offsets are unchanged and every digit stays in place)."""

    def at(i: int) -> str:
        return text[i] if 0 <= i < len(text) else ""

    chars: list[str] | None = None
    for p in joins:
        if at(p - 1) == "-" and at(p - 2) in _ASCII_DIGITS and at(p + 1) in _ASCII_DIGITS:
            lo = p - 1
        elif at(p - 1) in _ASCII_DIGITS and at(p + 1) == "-" and at(p + 2) in _ASCII_DIGITS:
            lo = p
        else:
            continue
        if chars is None:
            chars = list(text)
        chars[lo], chars[lo + 1] = "-", _JOIN
    return text if chars is None else "".join(chars)


def _digit_runs(text: str) -> list[list[tuple[int, int]]]:
    """Runs of digit groups joined by a single space or hyphen (or a hyphen and a marked
    join space), as (start, end) per group."""
    runs: list[list[tuple[int, int]]] = []
    prev_end = -3
    for m in _DIGIT_GROUP.finditer(text):
        start, end = m.span()
        if start == prev_end:
            runs[-1][-1] = (runs[-1][-1][0], end)
        elif 0 < start - prev_end <= 2 and text[prev_end:start] in _GROUP_SEPARATORS:
            runs[-1].append((start, end))
        else:
            runs.append([(start, end)])
        prev_end = end
    return runs


def _card_windows(
    text: str,
    run: Sequence[tuple[int, int]],
    accept: Callable[[int, int], bool] | None = None,
) -> list[tuple[int, int, int]]:
    """Luhn-valid 13-19 digit windows of ``run`` aligned to group boundaries, as (rank,
    first group, last group), sorted best first. Rank: card-shaped before not, then 16
    digits, then 15, then any length; ties go leftmost. A window whose (start, end) offsets
    ``accept`` rejects is left out."""
    bounds = [0]  # bounds[i] is the digit offset where group i starts.
    for start, end in run:
        bounds.append(bounds[-1] + end - start)
    if bounds[-1] < _CARD_MIN:
        return []
    values = [ord(ch) - 48 for start, end in run for ch in text[start:end]]
    # luhn[p][k] is the Luhn total (mod 10) of the digits before offset k, taking digits
    # whose index has parity p plain and the others doubled. A window [a, b) passes when
    # luhn[p][b] == luhn[p][a] for p = (b - 1) % 2, since its rightmost digit is plain.
    luhn = []
    for parity in (0, 1):
        totals, t = [0], 0
        for k, d in enumerate(values):
            t = (t + (d if k % 2 == parity else (d * 2 - 9 if d > 4 else d * 2))) % 10
            totals.append(t)
        luhn.append(totals)

    found: list[tuple[int, int, int]] = []
    groups = len(run)
    for i in range(groups):
        a = bounds[i]
        j = bisect_left(bounds, a + _CARD_MIN, i + 1) - 1
        while j < groups and bounds[j + 1] - a <= _CARD_MAX:
            b = bounds[j + 1]
            if b - a >= _CARD_MIN:
                totals = luhn[(b - 1) % 2]
                if totals[b] == totals[a] and (accept is None or accept(run[i][0], run[j][1])):
                    shape = ",".join(str(e - s) for s, e in run[i : j + 1])
                    rank = 0 if _CARD_SHAPE.fullmatch(shape) else 3
                    rank += 0 if b - a == 16 else 1 if b - a == 15 else 2
                    found.append((rank, i, j))
            j += 1
    found.sort()
    return found


def _choose_cards(windows: Sequence[tuple[int, int, int]], groups: int) -> list[tuple[int, int]]:
    """Card spans as (first group, last group), from ``windows`` sorted best first.

    Rank by rank: take each window that overlaps nothing chosen so far, leftmost first.
    Then a window of the same rank that overlaps a chosen one but also covers groups
    nothing has claimed is ambiguous (``1234`` + a 4-4-4-4 card can be valid both ways),
    so it is merged with what it overlaps rather than leaving possible card digits in
    clear. A window overlapping a better ranked span is dropped."""
    owner: list[int | None] = [None] * groups
    parent: list[int] = []
    ranks: list[int] = []

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def claim(rank: int, i: int, j: int, hit: set[int]) -> None:
        label = len(parent)
        parent.append(label)
        ranks.append(rank)
        for h in hit:
            parent[h] = label
        for k in range(i, j + 1):
            owner[k] = label

    start = 0
    while start < len(windows):
        rank = windows[start][0]
        stop = start
        while stop < len(windows) and windows[stop][0] == rank:
            stop += 1
        left: list[tuple[int, int]] = []
        for _, i, j in windows[start:stop]:
            if all(o is None for o in owner[i : j + 1]):
                claim(rank, i, j, set())
            else:
                left.append((i, j))
        for i, j in left:
            hit = {find(o) for o in owner[i : j + 1] if o is not None}
            if None in owner[i : j + 1] and all(ranks[h] == rank for h in hit):
                claim(rank, i, j, hit)
        start = stop

    spans: list[tuple[int, int]] = []
    prev = None
    for k, o in enumerate(owner):
        root = None if o is None else find(o)
        if root is not None and root == prev:
            spans[-1] = (spans[-1][0], k)
        elif root is not None:
            spans.append((k, k))
        prev = root
    return spans


def _is_one_number(run: Sequence[tuple[int, int]]) -> bool:
    return bool(_ONE_NUMBER_SHAPE.fullmatch(",".join(str(end - start) for start, end in run)))


def _digit_candidates(view: str, joins: Sequence[int]) -> list[_Span]:
    """SSN and phone matches in ``view`` (SSN first; phone over what SSN left), sorted by
    start. A phone's ``1``/``+1`` prefix is dropped when a segment join lies between it and
    the number, so it never comes from an earlier segment."""
    found: list[_Span] = []
    work = view
    for kind, pattern in _DIGIT_PASSES:
        new = []
        for m in pattern.finditer(work):
            start, end = m.span()
            prefix_end = m.end("prefix") if kind == PHONE else -1
            if prefix_end > start and bisect_right(joins, start) < bisect_left(joins, prefix_end):
                start = prefix_end
            new.append((start, end))
        found.extend((start, end, kind) for start, end in new)
        work = _mask(work, new)
    found.sort()
    return found


def _window_check(candidates: Sequence[_Span]) -> Callable[[int, int], bool]:
    """Acceptance test for a card window: it overlaps no SSN/phone candidate at all, so a
    phone or SSN next to a short number or a card keeps its label. Known gap, accepted: a
    hyphenated stray group glued to a card's first group (``034-6536 329989 72483``) is
    taken as a 7-digit phone, which refuses the card window."""
    starts = [start for start, _, _ in candidates]
    ends = [end for _, end, _ in candidates]

    def accept(start: int, end: int) -> bool:
        # Candidates are disjoint and sorted, so ends are sorted too.
        k = bisect_right(ends, start)
        return not (k < len(starts) and starts[k] < end)

    return accept


def _find(text: str, joins: Sequence[int] = ()) -> list[_Span]:
    """Non-overlapping PII spans in ``text``, sorted by start. ``joins`` are the offsets of
    the spaces that join segments."""
    found: list[_Span] = []
    work = text
    for kind, pattern in _EMAIL_PASSES:
        new = [(m.start(), m.end()) for m in pattern.finditer(work)]
        found.extend((start, end, kind) for start, end in new)
        work = _mask(work, new)

    view = _mark_joins(work, joins)
    candidates = _digit_candidates(view, joins)
    accept = _window_check(candidates)
    blocked: list[tuple[int, int]] = []
    for run in _digit_runs(view):
        cards = _choose_cards(_card_windows(view, run, accept), len(run))
        for i, j in cards:
            found.append((run[i][0], run[j][1], CARD))
            blocked.append((run[i][0], run[j][1]))
        if not cards and _is_one_number(run):
            blocked.append((run[0][0], run[-1][1]))
    # Candidates claim what cards and protected runs left. Both lists are sorted and
    # disjoint, so one forward sweep finds the overlaps.
    blocked.sort()
    b = 0
    for start, end, kind in candidates:
        while b < len(blocked) and blocked[b][1] <= start:
            b += 1
        if b < len(blocked) and blocked[b][0] < end:
            continue
        found.append((start, end, kind))
    found.sort()
    return found


def _counts(spans: Sequence[_Span]) -> dict[str, int]:
    counts = dict.fromkeys(TYPES, 0)
    for _, _, kind in spans:
        counts[kind] += 1
    return counts


def redact(text: str) -> tuple[str, dict[str, int]]:
    """``text`` with each PII value replaced by its placeholder, and counts by type."""
    texts, counts = redact_segments([text])
    return texts[0], counts


def redact_segments(texts: Sequence[str]) -> tuple[list[str], dict[str, int]]:
    """Redact ``texts`` as one string joined with a space, so a value split across
    segments is still found. A match crossing a boundary puts its placeholder in the
    segment where it starts and removes the rest from the following segment(s)."""
    joined = " ".join(texts)
    offsets, pos = [], 0
    for t in texts:
        offsets.append(pos)
        pos += len(t) + 1
    spans = _find(joined, [start - 1 for start in offsets[1:]])
    edits: list[list[tuple[int, int, str]]] = [[] for _ in texts]
    for start, end, kind in spans:
        first = bisect_right(offsets, start) - 1
        for i in range(first, len(texts)):
            seg_start, seg_end = offsets[i], offsets[i] + len(texts[i])
            if seg_start >= end:
                break
            lo, hi = max(start, seg_start) - seg_start, min(end, seg_end) - seg_start
            if i == first:
                edits[i].append((lo, hi, f"[{kind}]"))
            elif hi > lo:
                edits[i].append((lo, hi, ""))
    out = []
    for text, seg_edits in zip(texts, edits, strict=True):
        parts, pos = [], 0
        for lo, hi, replacement in seg_edits:
            parts += [text[pos:lo], replacement]
            pos = hi
        parts.append(text[pos:])
        out.append("".join(parts))
    return out, _counts(spans)
