import random
import re
import time

import pytest

from call_center.models import Transcript, TranscriptSegment
from call_center.pii import luhn_valid, redact, redact_segments
from call_center.stages import pii_redaction

UNBOUNDED = re.compile(r"(?<!\\)[*+](?![^\[]*\])|\{\d*,\}")
ZERO = {"SSN": 0, "CARD": 0, "EMAIL": 0, "PHONE": 0}


def _counts(**kwargs: int) -> dict[str, int]:
    return {**ZERO, **kwargs}


def _state(*texts: str) -> dict:
    segments = tuple(
        TranscriptSegment(speaker=f"speaker_{i % 2}", start=i, end=i + 0.5, text=t)
        for i, t in enumerate(texts)
    )
    return {"transcript": Transcript(segments=segments, audio_sha256="b" * 64)}


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("my social is 123-45-6789.", "my social is [SSN].", _counts(SSN=1)),
        ("my social is 123 45 6789", "my social is [SSN]", _counts(SSN=1)),
        ("card 4111 1111 1111 1111 thanks", "card [CARD] thanks", _counts(CARD=1)),
        ("card 4111-1111-1111-1111", "card [CARD]", _counts(CARD=1)),
        ("amex 378282246310005.", "amex [CARD].", _counts(CARD=1)),
        ("it's jane.doe+x@example.co.uk", "it's [EMAIL]", _counts(EMAIL=1)),
        ("mail JANE@Example.COM.", "mail [EMAIL].", _counts(EMAIL=1)),
        ("it's 123456789", "it's [SSN]", _counts(SSN=1)),
        ("(555) 123-4567", "[PHONE]", _counts(PHONE=1)),
        ("555.123.4567", "[PHONE]", _counts(PHONE=1)),
        ("+1 555 123 4567", "[PHONE]", _counts(PHONE=1)),
        ("555-0199", "[PHONE]", _counts(PHONE=1)),
        ("call 555-123-4567 now", "call [PHONE] now", _counts(PHONE=1)),
        ("call 5551234567", "call [PHONE]", _counts(PHONE=1)),
        ("call 1-800-555-0199.", "call [PHONE].", _counts(PHONE=1)),
        ("call +1 (555) 123-4567", "call [PHONE]", _counts(PHONE=1)),
    ],
)
def test_written_values_are_replaced(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jane doe at gmail dot com", "jane [EMAIL]"),
        ("Jane at Gmail Dot Com.", "[EMAIL]."),
        ("it is bob at mail dot co dot uk thanks", "it is [EMAIL] thanks"),
        ("sam at work dot io", "[EMAIL]"),
    ],
)
def test_spoken_email_is_replaced(text, expected):
    assert redact(text) == (expected, _counts(EMAIL=1))


def test_spoken_email_needs_a_known_tld():
    assert redact("meet me at the store dot xyz")[1] == ZERO


@pytest.mark.parametrize(
    "text",
    [
        "ref 1234 5678 9012 3456",
        "ref 1234567890123456",
        "ref 1234-5678-9012-3456",
        "ref 1234 5678 9012 3456 78",
        "ref 1234 567890 12345",
        "id 1234567890123",
        "id 1234567890123456789",
    ],
)
def test_card_failing_luhn_is_untouched(text):
    assert redact(text) == (text, ZERO)


def test_luhn_failing_run_not_shaped_like_one_number_is_checked_piece_by_piece():
    assert redact("ref 555 123 4567 1234") == ("ref [PHONE] 1234", _counts(PHONE=1))


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("ssn 123-45-6789 555-123-4567", "ssn [SSN] [PHONE]", _counts(SSN=1, PHONE=1)),
        ("call 555-123-4567 555-0199", "call [PHONE] [PHONE]", _counts(PHONE=2)),
        ("card 4111 1111 1111 1111 123", "card [CARD] 123", _counts(CARD=1)),
        ("card 4111-1111-1111-1111-123", "card [CARD]-123", _counts(CARD=1)),
        ("Option 2 4111 1111 1111 1111", "Option 2 [CARD]", _counts(CARD=1)),
        ("card 4111 1111 1111 1111 555-0199", "card [CARD] [PHONE]", _counts(CARD=1, PHONE=1)),
        ("4111 1111 1111 1111 123-45-6789", "[CARD] [SSN]", _counts(CARD=1, SSN=1)),
        (
            "cards 4111 1111 1111 1111 5555 5555 5555 4444",
            "cards [CARD] [CARD]",
            _counts(CARD=2),
        ),
        ("call 634-11-1263 288-857-1938 ok", "call [SSN] [PHONE] ok", _counts(SSN=1, PHONE=1)),
        ("call 912-656-5363 938-434-2674 ok", "call [PHONE] [PHONE] ok", _counts(PHONE=2)),
        ("x 123-45-6789 123-45-6789", "x [SSN] [SSN]", _counts(SSN=2)),
        ("x 123 45 6789 555 123 4567", "x [SSN] [PHONE]", _counts(SSN=1, PHONE=1)),
        ("x 123456789 5551234567", "x [SSN] [PHONE]", _counts(SSN=1, PHONE=1)),
        ("john.1234567890123@gmail.com", "[EMAIL]", _counts(EMAIL=1)),
        ("mail 4111111111111111@example.com", "mail [EMAIL]", _counts(EMAIL=1)),
    ],
)
def test_adjacent_values_are_all_replaced(text, expected, counts):
    assert redact(text) == (expected, counts)


def test_non_ascii_digits_do_not_crash():
    text = "ref \u0664\u0661\u0661\u0661 \u0661\u0661\u0661\u0661 x"
    assert redact(text) == (text, ZERO)


def test_card_in_odd_groups_with_a_phone_inside_is_redacted_as_the_phone():
    # Known gap, accepted: a card window may not overlap an SSN/phone candidate, so a card
    # read in odd groups that contain a phone-shaped piece is redacted as that piece.
    assert redact("card 411 111 111 1111 111") == ("card 411 [PHONE] 111", _counts(PHONE=1))


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("call 555-123-4567 1000", "call [PHONE] 1000", _counts(PHONE=1)),
        ("ssn 123-45-6789 1000", "ssn [SSN] 1000", _counts(SSN=1)),
        ("call 1000 555-123-4567", "call 1000 [PHONE]", _counts(PHONE=1)),
    ],
)
def test_card_window_never_overlaps_a_ssn_or_phone(text, expected, counts):
    assert redact(text) == (expected, counts)


def test_stray_group_before_card_does_not_join_it():
    assert redact_segments(["Option 2", "4804 0576 5019 6405"]) == (
        ["Option 2", "[CARD]"],
        _counts(CARD=1),
    )


def test_ambiguous_overlapping_card_readings_are_both_redacted():
    # A 4-digit group before a 4-4-4-4 card can itself start a valid 4-4-4-4 window; the
    # text cannot say which is the card, so the union is redacted rather than leaving card
    # digits in clear.
    card = ["4111", "1111", "1111", "1111"]
    pre = next(f"{n:04d}" for n in range(10_000) if luhn_valid(f"{n:04d}" + "".join(card[:3])))
    assert redact(f"x {pre} {' '.join(card)} ok") == ("x [CARD] ok", _counts(CARD=1))
    assert redact(f"x 1234 {' '.join(card)} ok") == ("x 1234 [CARD] ok", _counts(CARD=1))


def test_hyphenated_stray_group_glued_to_a_card_is_a_known_gap():
    # Known gap, accepted: "034-6536" is a 7-digit phone, and no card window may overlap
    # an SSN/phone candidate, so the rest of the card stays in clear.
    assert redact("x 034-6536 329989 72483 ok") == ("x [PHONE] 329989 72483 ok", _counts(PHONE=1))


def test_adjacent_cards_keep_two_labels():
    text = "cards 4111 1111 1111 1111 5555 5555 5555 4444"
    assert redact(text) == ("cards [CARD] [CARD]", _counts(CARD=2))


@pytest.mark.parametrize(
    "texts",
    [
        ["Press 1", "555 123 4567"],
        ["call +1", "555 123 4567"],
        ["call 1-", "555-123-4567"],
        ["dial 1-", "555-0199"],
    ],
)
def test_phone_prefix_never_comes_from_earlier_segment(texts):
    assert redact_segments(texts) == ([texts[0], "[PHONE]"], _counts(PHONE=1))


@pytest.mark.parametrize(
    ("texts", "expected", "counts"),
    [
        (["my ssn", "is 123-45-", "6789"], ["my ssn", "is [SSN]", ""], _counts(SSN=1)),
        (["call 555-", "0199 ok"], ["call [PHONE]", " ok"], _counts(PHONE=1)),
        (["call 555-123-", "4567"], ["call [PHONE]", ""], _counts(PHONE=1)),
        (["card 4111-1111-", "1111-1111"], ["card [CARD]", ""], _counts(CARD=1)),
        (["room 4-", "123-45-6789"], ["room 4-", "[SSN]"], _counts(SSN=1)),
        (["call 555-0199-", "1234"], ["call [PHONE]-", "1234"], _counts(PHONE=1)),
        (["ssn 123-45", "-6789"], ["ssn [SSN]", ""], _counts(SSN=1)),
        (["call 555", "-123-4567"], ["call [PHONE]", ""], _counts(PHONE=1)),
    ],
)
def test_hyphen_at_segment_end_joins_the_value(texts, expected, counts):
    assert redact_segments(texts) == (expected, counts)


def test_hyphen_space_inside_a_segment_is_not_a_separator():
    assert redact("ref 123-45- 6789") == ("ref 123-45- 6789", ZERO)


DIGITS = "0123456789"


def _digits(rng: random.Random, k: int) -> str:
    return "".join(rng.choices(DIGITS, k=k))


def _ssn_forms(d: str) -> list[str]:
    return [f"{d[:3]}-{d[3:5]}-{d[5:]}", f"{d[:3]} {d[3:5]} {d[5:]}", d]


def _phone_forms(d: str) -> list[str]:
    a, b, c = d[:3], d[3:6], d[6:]
    bodies = [f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}", f"{a} {b} {c}", d]
    prefixed = [p + body for body in bodies for p in ("+1 ", "1 ", "1-", "+1")]
    return bodies + prefixed + [f"{b}-{c}"]


def _random_value(rng: random.Random) -> tuple[str, str]:
    if rng.random() < 0.4:
        return "SSN", rng.choice(_ssn_forms(_digits(rng, 9)))
    return "PHONE", rng.choice(_phone_forms(_digits(rng, 10)))


def _valid_card(rng: random.Random, length: int) -> str:
    body = _digits(rng, length - 1)
    check = next(c for c in DIGITS if luhn_valid(body + c))
    return body + check


def _random_card(rng: random.Random) -> tuple[str, list[str]]:
    """A random Luhn-valid card in a random written form, and its digit groups."""
    form = rng.choice(["4444", "465", "unbroken"])
    if form == "4444":
        d = _valid_card(rng, 16)
        groups = [d[0:4], d[4:8], d[8:12], d[12:]]
    elif form == "465":
        d = _valid_card(rng, 15)
        groups = [d[0:4], d[4:10], d[10:]]
    else:
        groups = [_valid_card(rng, rng.randint(13, 19))]
    return rng.choice(" -").join(groups), groups


def _random_email(rng: random.Random) -> str:
    local = "".join(rng.choices("abcdefghij" + DIGITS + "._", k=rng.randint(1, 12)))
    if rng.random() < 0.5:
        return f"j{local}@example{rng.choice(['.com', '.co.uk', '.org'])}"
    return f"jane at mail{_digits(rng, 2)} dot {rng.choice(['com', 'co dot uk', 'io'])}"


def _expected_counts(*kinds: str) -> dict[str, int]:
    counts = dict(ZERO)
    for kind in kinds:
        counts[kind] += 1
    return counts


def test_property_adjacent_ssn_and_phone_values():
    rng = random.Random(3304)
    for _ in range(3_000):
        (kind_a, a), (kind_b, b) = _random_value(rng), _random_value(rng)
        counts = _expected_counts(kind_a, kind_b)
        assert redact(f"call {a} {b} ok") == (f"call [{kind_a}] [{kind_b}] ok", counts), (a, b)
        two = redact_segments([f"call {a}", f"{b} ok"])
        assert two == ([f"call [{kind_a}]", f"[{kind_b}] ok"], counts), (a, b)


def test_property_card_with_stray_groups_beside_it():
    rng = random.Random(3305)
    for _ in range(3_000):
        card, groups = _random_card(rng)
        pre = _digits(rng, rng.randint(1, 4)) if rng.random() < 0.7 else ""
        post = _digits(rng, rng.randint(1, 4)) if not pre or rng.random() < 0.5 else ""
        psep, qsep = rng.choice(" -"), rng.choice(" -")
        if len(pre) == 3 and len(groups) > 1 and card[4] == " ":
            # "ddd-dddd " is the known gap above (a 7-digit phone glued to the card).
            psep = " "
        left = f"{pre}{psep}" if pre else ""
        right = f"{qsep}{post}" if post else ""
        # Documented ambiguity: a 4-digit group beside a 4-4-4-4 card can form a second
        # valid card-shaped window; then both readings are redacted together.
        four = len(groups) == 4
        absorb_pre = four and len(pre) == 4 and luhn_valid(pre + "".join(groups[:3]))
        absorb_post = four and len(post) == 4 and luhn_valid("".join(groups[1:]) + post)
        expected = (
            f"x {'' if absorb_pre else left}[CARD]{'' if absorb_post else right} ok",
            _counts(CARD=1),
        )
        assert redact(f"x {left}{card}{right} ok") == expected, (left, card, right)


def test_property_ssn_or_phone_followed_by_a_short_number():
    rng = random.Random(3306)
    for _ in range(3_000):
        kind, value = _random_value(rng)
        group = _digits(rng, rng.randint(1, 6))
        counts = _expected_counts(kind)
        assert redact(f"call {value} {group} ok") == (f"call [{kind}] {group} ok", counts), (
            value,
            group,
        )
        two = redact_segments([f"call {value}", f"{group} ok"])
        assert two == ([f"call [{kind}]", f"{group} ok"], counts), (value, group)


def test_property_ssn_or_phone_followed_by_a_card():
    rng = random.Random(3308)
    for _ in range(3_000):
        kind, value = _random_value(rng)
        d = _valid_card(rng, 16)
        card = rng.choice(" -").join([d[0:4], d[4:8], d[8:12], d[12:]])
        counts = _expected_counts(kind, "CARD")
        assert redact(f"call {value} {card} ok") == (f"call [{kind}] [CARD] ok", counts), (
            value,
            card,
        )
        two = redact_segments([f"call {value}", f"{card} ok"])
        assert two == ([f"call [{kind}]", "[CARD] ok"], counts), (value, card)


def test_property_value_split_at_a_hyphen():
    rng = random.Random(3309)
    cases = 0
    while cases < 3_000:
        kind, value = _random_value(rng)
        # Not the hyphen of a "1-" prefix: a prefix never comes from an earlier segment.
        hyphens = [i for i, ch in enumerate(value) if ch == "-" and value[: i + 1] != "1-"]
        if not hyphens:
            continue
        cases += 1
        cut = rng.choice(hyphens) + rng.choice((0, 1))  # hyphen ends A or starts B
        texts = [f"call {value[:cut]}", f"{value[cut:]} ok"]
        result = redact_segments(texts)
        assert result == ([f"call [{kind}]", " ok"], _expected_counts(kind)), texts


def test_property_value_after_a_previous_segment():
    rng = random.Random(3307)
    endings = ["word", "{d}", "{d}-", "1", "1-"]
    for _ in range(4_000):
        roll = rng.random()
        if roll < 0.5:
            kind, value = _random_value(rng)
        elif roll < 0.8:
            kind, value = "CARD", _random_card(rng)[0]
        else:
            kind, value = "EMAIL", _random_email(rng)
        prev = "x " + rng.choice(endings).format(d=rng.choice(DIGITS))
        result = redact_segments([prev, f"{value} ok"])
        assert result == ([prev, f"[{kind}] ok"], _expected_counts(kind)), (prev, value)


def test_digit_in_previous_segment_does_not_hide_card():
    texts, counts = redact_segments(["Option 2", "4111 1111 1111 1111"])
    assert texts == ["Option 2", "[CARD]"]
    assert counts == _counts(CARD=1)


def test_card_with_cvv_in_next_segment():
    texts, counts = redact_segments(["card 4111 1111 1111 1111", "123 is the code"])
    assert texts == ["card [CARD]", "123 is the code"]
    assert counts == _counts(CARD=1)


@pytest.mark.parametrize(
    "text",
    [
        "1234-5678",
        "a 22345678901 b",
        "a 123456789012 b",
        "a 12345678901234567890 b",
        "x123-45-67890",
        "0123-45-6789",
        "5555-123-4567",
        "555-123-45678",
        "90210-1234",
    ],
)
def test_digit_matches_never_cut_a_longer_run(text):
    assert redact(text) == (text, ZERO)


@pytest.mark.parametrize(
    "text",
    [
        "I'll call you back in 5 minutes, order 42.",
        "It's 10:30 now, or 3:45 pm tomorrow.",
        "That comes to $1,299.99, or 49.95 a month.",
        "Order number 48213 shipped; order 7731 is pending.",
        "Back in 1999, then again in 2024.",
        "My PIN is 1234 and the code is 0000.",
        "The zip code is 90210, or 10001-0001.",
        "Call the date 2026-10-11 or 10/11/2026.",
        "Room 101, floor 3, extension 4417.",
        "Version 3.4.1 at 20 percent off.",
        "I'm at home, look at that dot, it's common.",
        "",
    ],
)
def test_benign_text_is_unchanged(text):
    assert redact(text) == (text, ZERO)


def test_mixed_segment_has_four_placeholders():
    text = "ssn 123-45-6789, card 4111 1111 1111 1111, mail jane@example.com, call (555) 123-4567"
    assert redact(text) == (
        "ssn [SSN], card [CARD], mail [EMAIL], call [PHONE]",
        _counts(SSN=1, CARD=1, EMAIL=1, PHONE=1),
    )


def test_whitespace_and_punctuation_are_byte_identical():
    text = "  Hi,\tmy number:\n555-123-4567!!  (thanks)  "
    assert redact(text)[0] == "  Hi,\tmy number:\n[PHONE]!!  (thanks)  "


def test_split_value_goes_to_starting_segment():
    texts, counts = redact_segments(["card is 4111 1111", "1111 1111 ok"])
    assert texts == ["card is [CARD]", " ok"]
    assert counts == _counts(CARD=1)


def test_split_value_across_three_segments():
    texts, counts = redact_segments(["ssn 123", "45", "6789 done"])
    assert texts == ["ssn [SSN]", "", " done"]
    assert counts == _counts(SSN=1)


def test_split_spoken_email():
    texts, _ = redact_segments(["write to jane at", "gmail dot com please"])
    assert texts == ["write to [EMAIL]", " please"]


def test_clean_segments_round_trip():
    texts = ["Thank you for calling.", "", "Order 42, please."]
    assert redact_segments(texts) == (texts, ZERO)


@pytest.mark.parametrize(
    ("digits", "valid"),
    [
        ("4111111111111111", True),
        ("378282246310005", True),
        ("5555555555554444", True),
        ("79927398713", True),
        ("4111111111111112", False),
        ("1234567890123456", False),
        ("", False),
        ("4111 1111", False),
        ("\u0664111111111111111", False),
    ],
)
def test_luhn(digits, valid):
    assert luhn_valid(digits) is valid


def test_card_windows_match_brute_force_luhn():
    from call_center.pii import _card_windows, _digit_runs

    rng = random.Random(33)
    for _ in range(2_000):
        groups = [_digits(rng, rng.randint(1, 6)) for _ in range(8)]
        text = " ".join(groups)
        [run] = _digit_runs(text)
        expected = {
            (i, j)
            for i in range(len(groups))
            for j in range(i, len(groups))
            if 13 <= len("".join(groups[i : j + 1])) <= 19
            and luhn_valid("".join(groups[i : j + 1]))
        }
        windows = _card_windows(text, run)
        assert {(i, j) for _, i, j in windows} == expected, text
        assert windows == sorted(windows)


def test_patterns_are_bounded():
    from call_center import pii

    for name in ("_DIGIT_GROUP", "_ONE_NUMBER_SHAPE", "_SSN", "_PHONE", "_EMAIL", "_SPOKEN_EMAIL"):
        assert not UNBOUNDED.search(getattr(pii, name).pattern), name


def test_large_text_scans_quickly():
    chunk = (
        "Thanks for calling, my ssn is 123-45-6789 and card 4111 1111 1111 1111, "
        "email jane@example.com or jane at gmail dot com, call 555-123-4567. "
        "Order 42 at 10:30 for $19.99, ref 1234 5678 9012 3456. "
    )
    text = (chunk * (200_000 // len(chunk) + 1))[:200_000]
    start = time.perf_counter()
    redacted, counts = redact(text)
    assert time.perf_counter() - start < 0.5
    assert "123-45-6789" not in redacted
    assert counts["CARD"] > 0
    # Pathological input: long runs that never complete a match.
    for bad in (
        "1 " * 100_000,
        "1-" * 100_000,
        "1234 " * 40_000,
        "a" * 200_000,
        "a." * 100_000,
        "x at " * 40_000,
    ):
        start = time.perf_counter()
        redact(bad)
        assert time.perf_counter() - start < 0.5


def test_stage_keeps_speaker_and_timing_and_audits_counts():
    state = _state("my ssn is 123-45-6789", "mail a@b.com or c@d.org", "call 555-0199")
    result = pii_redaction.run(state)
    redacted = result["redacted_transcript"]
    source = state["transcript"]
    assert redacted.audio_sha256 == source.audio_sha256
    assert [(s.speaker, s.start, s.end) for s in redacted.segments] == [
        (s.speaker, s.start, s.end) for s in source.segments
    ]
    assert [s.text for s in redacted.segments] == [
        "my ssn is [SSN]",
        "mail [EMAIL] or [EMAIL]",
        "call [PHONE]",
    ]
    assert result["stages_completed"] == ["pii_redaction"]
    [event] = result["audit"]
    assert (event.stage, event.outcome) == ("pii_redaction", "ok")
    assert event.detail == "redacted SSN 1, CARD 0, EMAIL 2, PHONE 1"


def test_stage_audit_never_contains_values():
    values = ["123-45-6789", "4111 1111 1111 1111", "jane@example.com", "555-123-4567"]
    result = pii_redaction.run(_state(*values))
    detail = result["audit"][0].detail
    for value in values:
        for fragment in re.split(r"[ @.-]", value):
            assert fragment not in detail


def test_stage_clean_transcript_is_equal():
    state = _state("Thank you for calling.", "Order 42, please.")
    redacted = pii_redaction.run(state)["redacted_transcript"]
    assert redacted == state["transcript"]


def test_stage_missing_transcript_gives_empty():
    result = pii_redaction.run({})
    assert result["redacted_transcript"].segments == ()
    assert result["audit"][0].detail == "redacted SSN 0, CARD 0, EMAIL 0, PHONE 0"
