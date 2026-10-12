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


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        # The tiny model's looped output for a card read aloud.
        ("my card number is " + "4" + "1" * 400, "my card number is [CARD]", _counts(CARD=1)),
        ("my card number is 4" + " one" * 400, "my card number is [CARD]", _counts(CARD=1)),
        ("the reference is 12345678901234567890.", "the reference is [CARD].", _counts(CARD=1)),
        ("ref 4539 12345678901234567890 ok", "ref [CARD] ok", _counts(CARD=1)),
        ("x 123-45-6789 " + "7" * 25 + " y", "x [CARD] y", _counts(CARD=1)),
        ("x 123-45-6789, " + "7" * 25 + " y", "x [SSN], [CARD] y", _counts(SSN=1, CARD=1)),
        # A loop that starts partway into a card hides the whole card.
        ("my card is 4539 1488 0343 6" + "4" * 30, "my card is [CARD]", _counts(CARD=1)),
        ("4539-1488-0343-64" + "6" * 30, "[CARD]", _counts(CARD=1)),
        ("4" * 30 + " 4539 1488 ok", "[CARD] ok", _counts(CARD=1)),
        # 19 digits or fewer: as before (protected when not Luhn-valid, a card when it is).
        ("the reference is 1234567890123456789.", "the reference is 1234567890123456789.", ZERO),
        ("ref 4539148803436460003 ok", "ref [CARD] ok", _counts(CARD=1)),
    ],
)
def test_unbroken_run_of_twenty_or_more_digits_is_a_card(text, expected, counts):
    assert redact(text) == (expected, counts)


def test_long_digit_run_split_across_segments():
    texts, counts = redact_segments(["card 4" + "1" * 30, "1" * 30 + " thanks"])
    assert texts == ["card [CARD]", " thanks"]
    assert counts == _counts(CARD=1)
    texts, counts = redact_segments(["card 4539 1488", "0343 6" + "4" * 30 + " ok"])
    assert texts == ["card [CARD]", " ok"]
    assert counts == _counts(CARD=1)


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


def test_hyphen_space_inside_a_segment_is_not_a_written_separator():
    # Not a 3.3 SSN (a hyphen then a space joins groups only at a segment join), so no
    # written value cuts the run; the dictated pass (story 7) redacts it whole.
    assert redact("ref 123-45- 6789") == ("ref [SSN]", _counts(SSN=1))


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
        "a 22345678901 b",
        "a 123456789012 b",
        "a 1234567890123456789 b",
        "x123-45-67890",
        "555-123-45678",
        "90210-1234",
    ],
)
def test_digit_matches_never_cut_a_longer_run(text):
    assert redact(text) == (text, ZERO)


@pytest.mark.parametrize("text", ["1234-5678", "0123-45-6789", "5555-123-4567"])
def test_digit_matches_never_cut_a_longer_run_of_short_groups(text):
    # No 3.3 match cuts the run; the dictated pass (story 7) redacts it whole.
    assert redact(text) == ("[PHONE]", _counts(PHONE=1))


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

    for name in (
        "_DIGIT_GROUP",
        "_ONE_NUMBER_SHAPE",
        "_SSN",
        "_PHONE",
        "_EMAIL",
        "_SPOKEN_EMAIL",
        "_DICTATION_TOKEN",
    ):
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
    # Degenerate inputs guard against super-linear blowup, not raw speed: tens of thousands
    # of one-digit groups in a single run take ~0.35 s locally and longer on a shared CI
    # runner, while anything quadratic would take minutes.
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
        assert time.perf_counter() - start < 2.0, bad[:12]


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


# Spoken numbers (story 3.4).


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        (
            "card four one one one one one one one one one one one one one one one thanks",
            "card [CARD] thanks",
            _counts(CARD=1),
        ),
        (
            "four one one one, one one one one, one one one one, one one one one.",
            "[CARD].",
            _counts(CARD=1),
        ),
        ("it's one two three, four five, six seven eight nine", "it's [SSN]", _counts(SSN=1)),
        ("five five five, one two three, four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("five five five oh one nine nine", "[PHONE]", _counts(PHONE=1)),
        ("double five five one two three four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("five five five twelve thirty four", "[PHONE]", _counts(PHONE=1)),
        ("one eight hundred five five five oh one nine nine", "[PHONE]", _counts(PHONE=1)),
        ("call 555 one two three 4567", "call [PHONE]", _counts(PHONE=1)),
        ("account one two three four five six seven eight", "account [PHONE]", _counts(PHONE=1)),
        ("ref one two three four five six seven eight nine", "ref [SSN]", _counts(SSN=1)),
        (
            "ref one two three four five six seven eight nine zero one two",
            "ref [CARD]",
            _counts(CARD=1),
        ),
        (
            "five five five... one two three... four five six seven",
            "[PHONE]",
            _counts(PHONE=1),
        ),
        (
            "five five five — one two three — four five six seven",
            "[PHONE]",
            _counts(PHONE=1),
        ),
        ("five five five - one two three - four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("five-five-five-one-two-three-four-five-six-seven", "[PHONE]", _counts(PHONE=1)),
        ("five five five one two three 4567", "[PHONE]", _counts(PHONE=1)),
        ("555-123 four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("five five five 1 2 3 4 5 6 7", "[PHONE]", _counts(PHONE=1)),
        ("call (555) one two three, four five six seven", "call [PHONE]", _counts(PHONE=1)),
        (
            "call (five five five) one two three four five six seven",
            "call [PHONE]",
            _counts(PHONE=1),
        ),
        ("(555) 123 four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("(555) one two three four five six seven", "[PHONE]", _counts(PHONE=1)),
        # Separator marks with whitespace between them.
        (
            "(five five five) (one two three) four five six seven",
            "[PHONE]",
            _counts(PHONE=1),
        ),
        ("(555) (123) four five six seven", "[PHONE]", _counts(PHONE=1)),
        (
            "five five five, - one two three four five six seven",
            "[PHONE]",
            _counts(PHONE=1),
        ),
        (
            "invoice 2024-01-15, five five five one two three four",
            "invoice 2024-01-15, [PHONE]",
            _counts(PHONE=1),
        ),
        (
            "for $19.99, one eight hundred five five five 0199.",
            "for $19.99, [PHONE].",
            _counts(PHONE=1),
        ),
        # Partly matched by a 3.3 shape: the rest of the run joins the value.
        ("five, five five one two three four five six seven", "[PHONE]", _counts(PHONE=1)),
        ("five five five one two three four five six, seven", "[PHONE]", _counts(PHONE=1)),
        (
            "four one one, one one one, one one one one, one one one one one one",
            "[CARD]",
            _counts(CARD=1),
        ),
        # Written digits that are not plain digit groups end a run.
        (
            "at 10:30 one two three four five six seven",
            "at 10:30 [PHONE]",
            _counts(PHONE=1),
        ),
        (
            "I paid 19.99 one two three four five six seven",
            "I paid 19.99 [PHONE]",
            _counts(PHONE=1),
        ),
        # A run redacted on its own stays a separate value beside a written one.
        (
            "123-45-6789 one two three four five six seven eight",
            "[SSN] [PHONE]",
            _counts(SSN=1, PHONE=1),
        ),
        (
            "five five five one two three four five six seven one 123-45-6789",
            "[PHONE] [SSN]",
            _counts(SSN=1, PHONE=1),
        ),
        # An uncovered stretch of 7+ digits (3+ from words) is a value of its own.
        (
            "one two three, four five, six seven eight nine, five five five oh one nine nine",
            "[SSN], [PHONE]",
            _counts(SSN=1, PHONE=1),
        ),
    ],
)
def test_spoken_values_are_replaced(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("card 4111-1111-1111-1111 two ok", "card [CARD] two ok", _counts(CARD=1)),
        ("call (555) 123-4567 one moment", "call [PHONE] one moment", _counts(PHONE=1)),
        ("my SSN is 123-45-6789 one moment", "my SSN is [SSN] one moment", _counts(SSN=1)),
        ("123-45-6789 one moment", "[SSN] one moment", _counts(SSN=1)),
        ("five five five 123-4567", "[PHONE]", _counts(PHONE=1)),
        ("five five five-123-4567 ok", "[PHONE] ok", _counts(PHONE=1)),
        ("4111 1111 1111 one one one one", "[CARD]", _counts(CARD=1)),
        ("call 555-123-4567, one two three", "call [PHONE]", _counts(PHONE=1)),
        ("call five five 123-4567", "call five five [PHONE]", _counts(PHONE=1)),
        ("call (five five five) 123-4567", "call [PHONE]", _counts(PHONE=1)),
        (
            "invoice 2024-01-15, five five five 123-4567",
            "invoice 2024-01-15, [PHONE]",
            _counts(PHONE=1),
        ),
    ],
)
def test_written_values_first_and_adjacent_spoken_runs(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    "text",
    [
        "one 2024-01-15",
        "on the twenty first 2024-01-15 order 12345678",
        "Flight UA123 one two three four",
        "code A1B2C3 one two three four five six",
        "It's 10:30, ten thirty, or five",
        "on 01-15-2024 one two three",
        "on 1-15-2024, one two three four",
    ],
)
def test_number_words_beside_written_numbers_that_are_not_values_are_unchanged(text):
    assert redact(text) == (text, ZERO)


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (
            ["my number is five five five one two", "three four five six seven ok"],
            ["my number is [PHONE]", " ok"],
        ),
        (["five five five", "-one two three four five six seven"], ["[PHONE]", ""]),
        (["five five five-", "one two three four five six seven"], ["[PHONE]", ""]),
        (["five five five,", "one two three four five six seven"], ["[PHONE]", ""]),
        (["call five five five one two three", "4567 ok"], ["call [PHONE]", " ok"]),
        (["call 555-123", "four five six seven ok"], ["call [PHONE]", " ok"]),
        (["(555", ") one two three four five six seven"], ["[PHONE]", ""]),
        (
            ["press double", "one five five five one two three four five six seven"],
            ["press double", "[PHONE]"],
        ),
        (["five five five", "123-4567 ok"], ["[PHONE]", " ok"]),
    ],
)
def test_spoken_phone_split_across_segments(texts, expected):
    assert redact_segments(texts) == (expected, _counts(PHONE=1))


def test_spoken_phone_prefix_never_comes_from_earlier_segment():
    # The 3.3 prefix rule holds in the reading (the phone found is "5551234567"), but a
    # run is redacted whole, so the stray "1" joins the value after it (the frozen rules'
    # accepted cost of a stray number joined to a value).
    texts = ["Press one", "five five five one two three four five six seven"]
    assert redact_segments(texts) == (["Press [PHONE]", ""], _counts(PHONE=1))


def test_spoken_and_written_values_in_one_text():
    text = (
        "ssn one two three, four five, six seven eight nine and card 4111 1111 1111 1111, "
        "phone five five five oh one nine nine or 555-123-4567, mail jane at gmail dot com"
    )
    assert redact(text) == (
        "ssn [SSN] and card [CARD], phone [PHONE] or [PHONE], mail [EMAIL]",
        _counts(SSN=1, CARD=1, EMAIL=1, PHONE=2),
    )


@pytest.mark.parametrize(
    ("texts", "expected", "counts"),
    [
        # Accepted cost (plan): a number word just after a spoken value with only a
        # separator between is taken with it.
        (["five five five oh one nine nine. One moment"], ["[PHONE] moment"], _counts(PHONE=1)),
        # Accepted cost (plan): a spoken year next to more digits is over-redacted.
        (["twenty twenty four, one two three"], ["[PHONE]"], _counts(PHONE=1)),
        (
            ["back in twenty twenty four", "ten o clock"],
            ["back in [PHONE]", " clock"],
            _counts(PHONE=1),
        ),
        # Accepted cost (plan): a stray number joined to a value may change its label.
        (["twenty", "five five five one two three four"], ["[SSN]", ""], _counts(SSN=1)),
    ],
)
def test_accepted_over_redaction(texts, expected, counts):
    assert redact_segments(texts) == (expected, counts)


SPOKEN_BENIGN = [
    "one moment",
    "I have two options",
    "back in twenty twenty four",
    "oh, okay",
    "ten o clock",
    "my PIN is one two three four",
    "Give me one second, please.",
    "It takes five or six days, maybe seven.",
    "Between two and three hundred dollars.",
    "We have twenty five minutes left.",
    "Chapter one, page twelve, line thirty-one.",
    "It costs nine ninety nine a month.",
    "I was born in nineteen eighty five.",
    "Option one, option two, or option three.",
    "For two to four weeks, I won.",
    "It's one o'clock, someone said so.",
    "Double check the triple A battery.",
    "Order 42 is one of two.",
    "About a hundred people, one or two hundred.",
    "Oh no, oh well, O.K.",
    "One, two, three, go!",
    "Press one - or two.",
    "Room 101, floor three, extension 4417.",
    "It's ten thirty, or five past eleven.",
    "one moment; two minutes... three hours",
    "Call (one) of us at ten, (two) at noon.",
    "one 2024-01-15",
    "on the twenty first 2024-01-15 order 12345678",
    "I'll be there in one or two minutes, maybe 15.",
    "It's 10:30, ten thirty, or five",
    "That's $19.99 for one, or 29.99 for two.",
    "Flight UA123 leaves at one, gate B12 at two.",
    "Give me two minutes, then three more.",
]


@pytest.mark.parametrize("text", SPOKEN_BENIGN)
def test_ordinary_number_words_are_unchanged(text):
    assert redact(text) == (text, ZERO)


def test_ordinary_number_words_across_segments_are_unchanged():
    texts = ["one moment", "two options", "back in twenty twenty four", "at noon"]
    assert redact_segments(texts) == (texts, ZERO)


UNIT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
ZERO_WORDS = ["zero", "oh", "o"]
TEEN_WORDS = [
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS_WORDS = {
    "2": "twenty",
    "3": "thirty",
    "4": "forty",
    "5": "fifty",
    "6": "sixty",
    "7": "seventy",
    "8": "eighty",
    "9": "ninety",
}
DIGIT_WORDS = {
    *UNIT_WORDS,
    *ZERO_WORDS,
    *TEEN_WORDS,
    *TENS_WORDS.values(),
    "hundred",
    "double",
    "triple",
}
# Between two groups of a spoken value. Whitespace alone between two number words adds
# nothing to the reading, so those groups read as one.
SPOKEN_SEPARATORS = [
    " ",
    "  ",
    ", ",
    ". ",
    "; ",
    ": ",
    "- ",
    ",\n",
    "... ",
    " - ",
    " — ",
    "—",
    "–",
    "-",
    ",",
    " , ",
]
# After a "(group" that opens a value.
CLOSING_SEPARATORS = [") ", "), ", ")-", ")—"]


def _unit_word(rng: random.Random, digit: str) -> str:
    return rng.choice(ZERO_WORDS) if digit == "0" else UNIT_WORDS[int(digit)]


def _combines(sep: str) -> bool:
    """True when a bare tens word before ``sep`` would join a unit word after it."""
    return sep == "-" or (sep.isspace() and len(sep) <= 3)


def _speak_group(rng: random.Random, d: str, bare_tens_at_end: bool) -> list[tuple[str, int]]:
    """``d`` read as number words, as (word, digit count) pairs. A bare tens word
    (``twenty``) is used only where no unit word can join it: before a zero, or at the end
    when ``bare_tens_at_end``."""
    words: list[tuple[str, int]] = []
    units: list[bool] = []  # whether each word is a single-digit word
    i = 0
    while i < len(d):
        rest, roll = d[i:], rng.random()
        bare_ok = len(rest) >= 2 and rest[0] in TENS_WORDS and rest[1] == "0"
        bare_ok = bare_ok and (rest[2:3] == "0" or (len(rest) == 2 and bare_tens_at_end))
        if len(rest) >= 3 and rest[0] == rest[1] == rest[2] and roll < 0.25:
            word, step, unit = f"triple {_unit_word(rng, rest[0])}", 3, False
        elif rest[:2] == "00" and len(words) >= 2 and units[-1] and roll < 0.5:
            word, step, unit = "hundred", 2, False
        elif len(rest) >= 2 and rest[0] == rest[1] and roll < 0.35:
            word, step, unit = f"double {_unit_word(rng, rest[0])}", 2, False
        elif len(rest) >= 2 and rest[0] == "1" and roll < 0.55:
            word, step, unit = TEEN_WORDS[int(rest[1])], 2, False
        elif len(rest) >= 2 and rest[0] in TENS_WORDS and rest[1] != "0" and roll < 0.7:
            word = TENS_WORDS[rest[0]] + rng.choice(" -") + UNIT_WORDS[int(rest[1])]
            step, unit = 2, False
        elif bare_ok and roll < 0.85:
            word, step, unit = TENS_WORDS[rest[0]], 2, False
        else:
            word, step, unit = _unit_word(rng, rest[0]), 1, True
        words.append((word, step))
        units.append(unit)
        i += step
    if rng.random() < 0.2:
        words[0] = (words[0][0].capitalize(), words[0][1])
    return words


def _random_spoken_value(rng: random.Random) -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.3:
        return "SSN", _digits(rng, 9)
    if roll < 0.6:
        return "PHONE", _digits(rng, 10)
    if roll < 0.85:
        return "CARD", _valid_card(rng, 16)
    return "CARD", _valid_card(rng, 15)


class _Value:
    """A value read out in random groups, some of them written as digits.

    ``atoms`` are the pieces of the value in order: ("group", digits, written, words) and
    ("sep", text). A segment join may go at a separator or between two words of a spoken
    group."""

    def __init__(self, rng: random.Random, kind: str, d: str):
        self.kind, self.d = kind, d
        cuts = sorted(rng.sample(range(1, len(d)), rng.randint(0, min(6, len(d) - 1))))
        self.cuts = cuts
        bounds = [0, *cuts, len(d)]
        groups = [d[a:b] for a, b in zip(bounds, bounds[1:], strict=False)]
        while True:
            written = [False] * len(groups)
            for k, g in enumerate(groups):
                if len(g) <= 6 and not (k and written[k - 1]) and rng.random() < 0.25:
                    written[k] = True
            if sum(len(g) for g, w in zip(groups, written, strict=True) if not w) >= 3:
                break
        self.wrap = len(groups) > 1 and not written[0] and rng.random() < 0.15
        seps = [
            rng.choice(CLOSING_SEPARATORS if k == 1 and self.wrap else SPOKEN_SEPARATORS)
            for k in range(1, len(groups))
        ]
        atoms: list[tuple] = []
        for k, g in enumerate(groups):
            if k:
                atoms.append(("sep", seps[k - 1]))
            if written[k]:
                atoms.append(("group", g, True, None))
                continue
            # The value ends with this group, or what follows cannot join a bare tens word.
            at_end = k == len(groups) - 1 or written[k + 1] or not _combines(seps[k])
            atoms.append(("group", g, False, _speak_group(rng, g, at_end)))
        self.atoms = atoms

    def split_points(self) -> list[tuple[int, int]]:
        """Where a segment join may go: (atom index, word index); word index -1 for a
        separator atom."""
        points = []
        for a, atom in enumerate(self.atoms):
            if atom[0] == "sep":
                points.append((a, -1))
            elif not atom[2]:
                points += [(a, w) for w in range(1, len(atom[3])) if atom[3][w][0] != "hundred"]
        return points


def _render(rng: random.Random, prefix: str, values: list[_Value], split, suffix: str):
    """The segments, and each value's run as the test reads it: (reading groups, start of
    the opening parenthesis or None, offset of the closing one or None). A reading group is
    [digits, [(token start, token end, digit count, spoken)], from a join]. ``split`` is
    (value index, atom index, word index) or None."""
    segments = [prefix]
    pos = len(prefix)  # offset in the joined text
    runs = []

    def add(text: str) -> None:
        nonlocal pos
        segments[-1] += text
        pos += len(text)

    def join(tail: str, head: str) -> None:
        nonlocal pos
        add(tail)
        segments.append("")
        pos += 1
        add(head)

    for v_index, value in enumerate(values):
        if v_index:
            add(" and ")
        opened = None
        if value.wrap:
            opened = pos
            add("(")
        groups: list[list] = []
        # Whether the next token starts a new reading group, and whether by a join.
        new_group, by_join = True, False
        prev_written = False
        close = None
        for a, atom in enumerate(value.atoms):
            here = split is not None and split[0] == v_index and split[1] == a
            if atom[0] == "sep":
                sep = atom[1]
                if value.wrap and close is None:
                    close = pos
                if here:
                    if sep.strip() and rng.random() < 0.5:
                        join(sep.rstrip(), "")
                    else:
                        join("", sep.strip())
                else:
                    add(sep)
                # Whitespace alone between two number words adds nothing.
                new_group = new_group or here or not sep.isspace() or prev_written
                by_join = by_join or here
                continue
            _, digits, written, words = atom
            pieces = [(digits, len(digits))] if written else words
            if written:
                new_group = True
            for w, (word, count) in enumerate(pieces):
                if w:
                    if here and split[2] == w:
                        join("", "")
                        new_group, by_join = True, True
                    else:
                        add(" ")
                token_start = pos
                add(word)
                if new_group:
                    groups.append(["", [], by_join])
                groups[-1][0] += digits if written else ""
                groups[-1][1].append((token_start, pos, count, not written))
                new_group, by_join = written, False
            prev_written = written
        runs.append((groups, opened, close))
    add(suffix)
    return segments, runs


def _expected_spans(groups: list[list], opened: int | None, close: int | None, d: str):
    """A spoken run's expected spans by the frozen rules: its reading goes through the 3.3
    detection unchanged, then the whole-run rule, labels by digit count, token-wide
    placeholders and the parenthesis rule."""
    from call_center.pii import _digit_spans

    # The reading, and for each digit its token and whether it is spoken.
    view, joins, digit_tokens = "", [], []
    k = 0
    for g, (_, tokens, from_join) in enumerate(groups):
        if g:
            if from_join:
                joins.append(len(view))
            view += " "
        for start, end, count, spoken in tokens:
            view += d[k : k + count]
            digit_tokens += [(start, end, spoken)] * count
            k += count
    assert k == len(d)
    at = [i for i, ch in enumerate(view) if ch != " "]  # view offset of each digit
    values = [(at.index(s), at.index(e - 1)) for s, e, _ in _digit_spans(view, joins)]

    def spoken(lo: int, hi: int) -> int:
        return sum(digit_tokens[i][2] for i in range(lo, hi + 1))

    # Whole-run rule, over digit indices.
    entries: list[list[int]] = []
    if not values:
        assert len(d) >= 7 and spoken(0, len(d) - 1) >= 3
        entries = [[0, len(d) - 1]]
    else:
        pieces, pos = [], 0
        for lo, hi in values:
            if pos < lo:
                pieces.append(("stretch", pos, lo - 1))
            pieces.append(("value", lo, hi))
            pos = hi + 1
        if pos < len(d):
            pieces.append(("stretch", pos, len(d) - 1))
        before, leading = None, None
        for kind, lo, hi in pieces:
            if kind == "value":
                entry = [leading if leading is not None else lo, hi]
                leading = None
                entries.append(entry)
                before = entry
            elif hi - lo + 1 >= 7 and spoken(lo, hi) >= 3:
                entries.append([lo, hi])
            elif before is not None:
                before[1] = hi
            else:
                leading = lo
    spans = []
    for lo, hi in entries:
        count = hi - lo + 1
        label = "SSN" if count == 9 else "CARD" if count >= 12 else "PHONE"
        start, end = digit_tokens[lo][0], digit_tokens[hi][1]
        if opened is not None and start == opened + 1 and close is not None and end > close:
            start = opened
        if spans and start < spans[-1][1]:
            start = spans[-1][1]  # A word shared by two values goes to the first.
        if start < end:
            spans.append((start, end, label))
    return spans


def _apply(texts: list[str], spans) -> list[str]:
    """The 3.3 segment rule: the placeholder goes where the span starts; the rest of the
    span is removed from later segments."""
    offsets, pos = [], 0
    for t in texts:
        offsets.append(pos)
        pos += len(t) + 1
    out = list(texts)
    for start, end, kind in sorted(spans, reverse=True):
        for i in reversed(range(len(texts))):
            lo = max(start, offsets[i]) - offsets[i]
            hi = min(end, offsets[i] + len(texts[i])) - offsets[i]
            if offsets[i] <= start < offsets[i] + len(texts[i]) + 1:
                out[i] = out[i][:lo] + f"[{kind}]" + out[i][hi:]
            elif offsets[i] > start and hi > lo:
                out[i] = out[i][:lo] + out[i][hi:]
    return out


def _no_digit_words(texts: list[str]) -> bool:
    return not (DIGIT_WORDS & set(re.split(r"[^a-z]+", " ".join(texts).casefold())))


def test_property_spoken_values():
    rng = random.Random(3310)
    phone_cuts: set[int] = set()
    ssn_cuts: set[int] = set()
    amex_groupings: set[tuple[int, ...]] = set()
    mixed = split_words = 0
    for _ in range(2_500):
        values = [_Value(rng, *_random_spoken_value(rng)) for _ in range(2)]
        split = None
        if rng.random() < 0.6:
            v = rng.randrange(2)
            points = values[v].split_points()
            if points:
                split = (v, *rng.choice(points))
                split_words += split[2] >= 0
        texts, runs = _render(rng, "call ", values, split, " ok")
        spans = [
            span
            for value, (groups, opened, close) in zip(values, runs, strict=True)
            for span in _expected_spans(groups, opened, close, value.d)
        ]
        for value in values:
            if value.kind == "PHONE":
                phone_cuts.update(value.cuts)
            elif value.kind == "SSN":
                ssn_cuts.update(value.cuts)
            if len(value.d) == 15:
                amex_groupings.add(tuple(value.cuts))
            mixed += any(atom[0] == "group" and atom[2] for atom in value.atoms)
        expected = (_apply(texts, spans), _expected_counts(*(kind for _, _, kind in spans)))
        result = redact_segments(texts)
        assert result == expected, texts
        assert _no_digit_words(result[0]), texts
    assert phone_cuts == set(range(1, 10))
    assert ssn_cuts == set(range(1, 9))
    assert len(amex_groupings) > 100
    assert mixed > 1_000 and split_words > 300


def _random_written_value(rng: random.Random) -> tuple[str, str]:
    if rng.random() < 0.7:
        return _random_value(rng)
    return "CARD", _random_card(rng)[0]


def _spoken_stretch(rng: random.Random, lo: int, hi: int) -> str:
    return " ".join(w for w, _ in _speak_group(rng, _digits(rng, rng.randint(lo, hi)), True))


def test_property_written_value_beside_a_short_spoken_stretch():
    rng = random.Random(3311)
    for _ in range(2_500):
        kind, value = _random_written_value(rng)
        spoken = _spoken_stretch(rng, 1, 2)
        sep = rng.choice([" ", ", ", " - ", "; ", "-", "... "])
        if rng.random() < 0.5:
            text, expected = f"call {spoken}{sep}{value} ok", f"call {spoken}{sep}[{kind}] ok"
        else:
            text, expected = f"call {value}{sep}{spoken} ok", f"call [{kind}]{sep}{spoken} ok"
        assert redact(text) == (expected, _expected_counts(kind)), text


def test_property_written_value_absorbs_a_spoken_stretch_of_three_or_more():
    rng = random.Random(3312)
    for _ in range(2_500):
        kind, value = _random_written_value(rng)
        spoken = _spoken_stretch(rng, 3, 6)
        sep = rng.choice([" ", ", ", " - ", "; ", "-", "... "])
        before = rng.random() < 0.5
        text = f"call {spoken}{sep}{value} ok" if before else f"call {value}{sep}{spoken} ok"
        result = redact(text)
        assert result == (f"call [{kind}] ok", _expected_counts(kind)), text
        assert _no_digit_words([result[0]]), text


def test_spoken_text_scans_quickly():
    chunk = (
        "my card is four one one one, one one one one, one one one one, one one one one, "
        "ssn one two three four five six seven eight nine, call double five five oh one "
        "nine nine, one moment, two options, back in twenty twenty four at ten o clock. "
        "Order 42 at 10:30 for $19.99, one eight hundred five five five 0199. "
    )
    text = (chunk * (200_000 // len(chunk) + 1))[:200_000]
    start = time.perf_counter()
    redacted, counts = redact(text)
    assert time.perf_counter() - start < 0.5
    assert "four one one one" not in redacted
    assert counts["CARD"] > 0 and counts["SSN"] > 0 and counts["PHONE"] > 0
    # Degenerate inputs guard against super-linear blowup, not raw speed: tens of thousands
    # of one-digit groups in a single run take ~0.35 s locally and longer on a shared CI
    # runner, while anything quadratic would take minutes.
    for bad in (
        "one " * 50_000,
        "1 one 2 two " * 15_000,
        "one, " * 40_000,
        "one-" * 40_000,
        "(one) " * 30_000,
        "twenty " * 30_000,
        "double " * 30_000,
        "one 1 " * 20_000,
        "UA1 one " * 20_000,
    ):
        start = time.perf_counter()
        redact(bad)
        assert time.perf_counter() - start < 2.0, bad[:12]


def test_many_segments_with_number_words_only_at_the_ends_scan_quickly():
    texts = ["one", *["hello there friend, how are you"] * 3_000, "two"]
    start = time.perf_counter()
    assert redact_segments(texts) == (texts, ZERO)
    assert time.perf_counter() - start < 0.5
    texts = ["five five five", *[""] * 3_000, "one two three four"]
    start = time.perf_counter()
    redacted, counts = redact_segments(texts)
    assert time.perf_counter() - start < 0.5
    assert (redacted[0], counts) == ("[PHONE]", _counts(PHONE=1))


def test_stage_redacts_spoken_values_and_counts_them():
    state = _state(
        "my card is four one one one one one one one one one one one one one one one",
        "and my social is one two three, four five, six seven eight nine",
        "call me on five five five, one two three, four five six seven, thanks",
    )
    result = pii_redaction.run(state)
    assert [s.text for s in result["redacted_transcript"].segments] == [
        "my card is [CARD]",
        "and my social is [SSN]",
        "call me on [PHONE], thanks",
    ]
    assert result["audit"][0].detail == "redacted SSN 1, CARD 1, EMAIL 0, PHONE 1"


# Dictated digits (story 7): short digit groups split by commas, dots or hyphen fragments.

ASR_PROBES = [
    # Real tiny-model outputs from ``say`` probes (2026-10-12).
    ("4-5-39, 1-48-8, 0-3-4-3, 6-4-6-7.", "[CARD].", _counts(CARD=1)),
    ("5 4 2 5, 2 3 3 4, 3 0 1 0, 9 9 0 3.", "[CARD].", _counts(CARD=1)),
    ("4.539, 1.488, 0.343, 6.467.", "[CARD].", _counts(CARD=1)),
    ("1, 2, 3, 4, 5, 6, 7, 8, 9.", "[SSN].", _counts(SSN=1)),
]


@pytest.mark.parametrize(("text", "expected", "counts"), ASR_PROBES)
def test_real_asr_dictated_values_are_redacted(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("4539, 1488, 0343, 6467", "[CARD]", _counts(CARD=1)),
        ("555, 212, 4367", "[PHONE]", _counts(PHONE=1)),
        ("123. 45. 6789", "[SSN]", _counts(SSN=1)),
        ("555-212, 4367", "[PHONE]", _counts(PHONE=1)),
        ("It's 4-5-39, 1-48-8, 0-3-4-3, 6-4-6-7, thanks", "It's [CARD], thanks", _counts(CARD=1)),
        ("card 4.539,1.488,0.343,6.467 ok", "card [CARD] ok", _counts(CARD=1)),
        ("ssn 1 2 3, 4 5, 6 7 8 9 ok", "ssn [SSN] ok", _counts(SSN=1)),
        ("call 555. 1234 now", "call [PHONE] now", _counts(PHONE=1)),
        # A date-like shape without a 4-digit year is read as its groups.
        ("1-15-24, 3 4 5 6", "[SSN]", _counts(SSN=1)),
        ("4-5, 1-15-24", "[PHONE]", _counts(PHONE=1)),
        # Only a currency sign makes an amount; a bare decimal is groups.
        ("4539, 1488, 0343, 6467, 19.99", "[CARD]", _counts(CARD=1)),
        ("4.53, 9.14, 88 ok", "[PHONE] ok", _counts(PHONE=1)),
        ("4539, 1488, 0343, 6467, $19.99", "[CARD], $19.99", _counts(CARD=1)),
    ],
)
def test_comma_and_dot_groups_are_redacted(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("It's 1-2-3-4-5-6-7-8-9", "It's [SSN]", _counts(SSN=1)),
        ("call 555 1234 today", "call [PHONE] today", _counts(PHONE=1)),
        ("(555), 212, 4367", "[PHONE]", _counts(PHONE=1)),
        ("call (555) 21 2 4367 now", "call [PHONE] now", _counts(PHONE=1)),
        ("ssn 1 2 3 4 5 6 7 8 9 ok", "ssn [SSN] ok", _counts(SSN=1)),
    ],
)
def test_hyphen_and_space_fragments_are_redacted(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("ssn 1-23-45 6789", "ssn [SSN]", _counts(SSN=1)),
        ("ssn 1-23-45 6-7-8-9", "ssn [SSN]", _counts(SSN=1)),
        ("ssn 1.2.3.4.5.6.7.8.9", "ssn [SSN]", _counts(SSN=1)),
        ("ssn 1, 2, 3, 4, 5, 6, 7, 8.9", "ssn [SSN]", _counts(SSN=1)),
        ("card 4539, 1488, 0343, 6467.5", "card [CARD]", _counts(CARD=1)),
        ("4.539, 1.488, 0.343, 6.46", "[CARD]", _counts(CARD=1)),
    ],
)
def test_review_pass_1_leaks_are_redacted(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("acct 1234-567-89012", "acct [CARD]", _counts(CARD=1)),
        ("ref 12345-1234-567", "ref [CARD]", _counts(CARD=1)),
        ("order 98765 4321 123", "order [CARD]", _counts(CARD=1)),
    ],
)
def test_dictated_run_is_never_cut_by_a_long_group(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    "text",
    [
        "1234-567-89012-345-6789",
        "123 4567 89012 345 6789",
        "12-345-67890 1234 567",
        "1 23456 7 8 9 0 1 2 3",
    ],
)
def test_chain_of_runs_and_long_groups_is_one_value(text):
    assert redact(text) == ("[CARD]", _counts(CARD=1))


def test_chain_across_a_segment_join_is_one_value():
    texts = ["call 555 1234", "89012 1 2 3 4 5 6 7"]
    assert redact_segments(texts) == (["call [CARD]", ""], _counts(CARD=1))


def test_comma_thousands_never_starts_after_a_decimal_point():
    assert redact("4.539,148,803") == ("[PHONE]", _counts(PHONE=1))
    assert redact("1,250,000 customers") == ("1,250,000 customers", ZERO)


def test_long_group_across_a_segment_join_is_covered():
    texts = ["acct 1234-567", "89012 ok"]
    assert redact_segments(texts) == (["acct [CARD]", " ok"], _counts(CARD=1))


def test_hyphen_fragments_split_across_segments():
    texts = ["my social is 1-2-3", "4-5-6-7-8-9 thanks"]
    assert redact_segments(texts) == (["my social is [SSN]", " thanks"], _counts(SSN=1))


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1112",
        "ref 4111-1111-1111-1112 ok",
        "ref 1234 567890 12345",
        "ref 1234 5678 9012 3456 7",
        "ref 1234567890123456",
        "ref 1234 5678 9012 3456, 7",
    ],
)
def test_runs_protected_as_one_number_are_kept(text):
    assert redact(text) == (text, ZERO)


def test_dictated_value_split_across_segments():
    texts = ["card 4 5 3 9, 1 4 8 8,", "0 3 4 3, 6 4 6 7 ok"]
    assert redact_segments(texts) == (["card [CARD]", " ok"], _counts(CARD=1))


@pytest.mark.parametrize(
    ("texts", "expected", "counts"),
    [
        (["ssn 123,", "45, 6789 ok"], ["ssn [SSN]", " ok"], _counts(SSN=1)),
        (["ssn 123", ", 45. 6789"], ["ssn [SSN]", ""], _counts(SSN=1)),
        (["call 555-", "212, 4367"], ["call [PHONE]", ""], _counts(PHONE=1)),
        (["4.539, 1.488,", "0.343,", "6.467."], ["[CARD]", "", "."], _counts(CARD=1)),
        # A segment join alone joins two groups; the comma sits elsewhere.
        (["call 555, 21", "2 4367"], ["call [PHONE]", ""], _counts(PHONE=1)),
    ],
)
def test_dictated_value_across_segment_joins(texts, expected, counts):
    assert redact_segments(texts) == (expected, counts)


@pytest.mark.parametrize(
    "text",
    [
        "options 1, 2, 3",
        "rooms 4.5, 6",
        "pick 1, 2, or 3",
        "$1,234.56",
        "1,250,000 customers",
        "on 1.15.2024",
        "at 10:30, 11:45",
        "Due 2024-01-15, 1234",
        "dob 1-15-1980, 1234",
        "on 1.15.2024. 3 4 5",
    ],
)
def test_short_lists_and_formatted_numbers_are_unchanged(text):
    assert redact(text) == (text, ZERO)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        # Accepted cost (plan): a comma list of short numbers with 7+ digits in all.
        ("rooms 101, 102, 103", "rooms [SSN]", _counts(SSN=1)),
        ("1, 2, 3, 4, 5, 6, 7", "[PHONE]", _counts(PHONE=1)),
        ("page 12 13 14 15", "page [PHONE]", _counts(PHONE=1)),
        ("in 2019, 2020 and 2021", "in [PHONE] and 2021", _counts(PHONE=1)),
        ("rates 1.25, 2.50, 3.75", "rates [SSN]", _counts(SSN=1)),
    ],
)
def test_long_short_number_lists_are_redacted_accepted_cost(text, expected, counts):
    assert redact(text) == (expected, counts)


@pytest.mark.parametrize(
    ("text", "expected", "counts"),
    [
        ("555-212-4367, 8", "[PHONE], 8", _counts(PHONE=1)),
        ("my SSN is 123-45-6789, 12", "my SSN is [SSN], 12", _counts(SSN=1)),
        ("card 4111 1111 1111 1111, 12, 3", "card [CARD], 12, 3", _counts(CARD=1)),
    ],
)
def test_earlier_values_are_unchanged_and_short_rest_kept(text, expected, counts):
    assert redact(text) == (expected, counts)


DICTATION_BENIGN = [
    "options 1, 2, 3, or 4",
    "rooms 4.5, 6",
    "That's $1,234.56, $2,000.00 and $15.",
    "We have 1,250,000 customers and 2,500,000 users.",
    "It's 10:30, 11:45 or 12:15, maybe 1:30.",
    "Due on 1.15.2024 or 2024-01-15, or 1/15/2024.",
    "Version 3.4.1, 2.0",
    "scores 9.5, 8.75",
    "between 10 and 20, or 30, 40",
    "Flights UA123, BA456, LH789.",
    "Order 48213, 7731.",
    "Ticket #12345, 678.",
    "It costs 19.99, or 29.99, or 4.99.",
    "Steps 1, 2 and 3. Then 4, 5.",
    "Page 12, line 3.",
]


@pytest.mark.parametrize("text", DICTATION_BENIGN)
def test_dictation_benign_text_is_unchanged(text):
    assert redact(text) == (text, ZERO)


DICTATION_SEPARATORS = {
    "mixed": [", ", ",", ". ", ".", " , ", ",  ", ", -", "-", " ", " - ", "- ", ") ", " (", "), "],
    "hyphen": ["-"],
    "space": [" "],
}


def _dictated_value(rng: random.Random) -> tuple[str, str]:
    """Random digits of a card, SSN or phone, and the kind they are labelled."""
    roll = rng.random()
    if roll < 0.4:
        d = _valid_card(rng, rng.choice([16, 16, 15, 13, 14, 17, 18, 19]))
    elif roll < 0.65:
        d = _digits(rng, 9)
    else:
        d = rng.choice(["", "1"]) + _digits(rng, rng.choice([7, 10, 10]))
    kind = "SSN" if len(d) == 9 else "CARD" if len(d) >= 12 else "PHONE"
    return kind, d


def _plainly_dictated(texts: list[str]) -> bool:
    """True when the rendering holds no shape the dictated pass treats as non-plain, no
    written value the 3.3 passes would take first, and no run 3.3 protects as one number."""
    from call_center import pii

    joined = " ".join(texts)
    joins, pos = [], 0
    for t in texts[:-1]:
        pos += len(t)
        joins.append(pos)
        pos += 1
    protected: list[tuple[int, int]] = []
    if pii._digit_spans(pii._mark_joins(joined, joins), joins, protected) or protected:
        return False
    for m in pii._DICTATION_TOKEN.finditer(joined):
        if m.lastgroup in ("amount", "time", "thousands", "long"):
            return False
        if m.lastgroup == "date" and pii._valid_date(m.group()):
            return False
    return True


def _render_dictation(
    rng: random.Random, d: str, prefix: str, suffix: str, style: str
) -> list[str]:
    """``d`` as random groups of 1-4 digits with random separators of ``style`` (mixed,
    hyphen-only or space-only), split into 1-3 segments at random separators or inside
    groups."""
    groups, i = [], 0
    while i < len(d):
        n = rng.randint(1, 4)
        groups.append(d[i : i + n])
        i += n
    seps = [rng.choice(DICTATION_SEPARATORS[style]) for _ in groups[1:]]
    pieces = [groups[0]]
    for sep, group in zip(seps, groups[1:], strict=True):
        pieces += [sep, group]
    # Split points: inside a separator, or between two digits of a group.
    cuts = rng.sample(range(1, len(pieces)), k=min(rng.choice([0, 0, 1, 1, 2]), len(pieces) - 1))
    texts, current = [], prefix
    for k, piece in enumerate(pieces):
        if k in cuts:
            at = rng.randint(0, len(piece)) if k % 2 else rng.randint(1, max(1, len(piece) - 1))
            if not k % 2 and len(piece) < 2:
                at = 0
            texts.append(current + piece[:at])
            current = piece[at:]
        else:
            current += piece
    texts.append(current + suffix)
    return texts


# A date-like shape without a 4-digit year, read as ordinary groups.
DATE_LIKE = re.compile(r"(?<![0-9])[0-9]{1,2}[-.][0-9]{1,2}[-.][0-9]{2}(?![0-9])")


def test_property_dictated_values():
    rng = random.Random(3313)
    checked = split = 0
    kinds: set[str] = set()
    styles: dict[str, int] = dict.fromkeys(DICTATION_SEPARATORS, 0)
    date_like = trailing_decimal = 0
    while checked < 3_000:
        kind, d = _dictated_value(rng)
        prefix = rng.choice(["card ", "my number is ", "it's ", "ssn: ", ""])
        suffix = rng.choice([" ok", ".", ", thanks", "", "!"])
        style = rng.choice(list(DICTATION_SEPARATORS))
        texts = _render_dictation(rng, d, prefix, suffix, style)
        if not _plainly_dictated(texts):
            continue
        checked += 1
        styles[style] += 1
        joined = " ".join(texts)
        date_like += DATE_LIKE.search(joined) is not None
        trailing_decimal += re.search(r"[0-9]\.[0-9]{1,2}(?:\.|\W*$|\W+[a-z])", joined) is not None
        split += len(texts) > 1
        kinds.add(kind)
        expected = [prefix + f"[{kind}]"] + [""] * (len(texts) - 2) + [suffix]
        if len(texts) == 1:
            expected = [prefix + f"[{kind}]" + suffix]
        assert redact_segments(texts) == (expected, _expected_counts(kind)), texts
        assert re.sub(r"\D", "", "".join(texts)) == d
    assert kinds == {"CARD", "SSN", "PHONE"}
    assert split > 1_000
    assert min(styles.values()) > 600, styles
    assert date_like > 60 and trailing_decimal > 30, (date_like, trailing_decimal)


def test_dictation_scans_quickly():
    chunk = (
        "my card is 4-5-39, 1-48-8, 0-3-4-3, 6-4-6-7. ssn 1, 2, 3, 4, 5, 6, 7, 8, 9. "
        "or 4.539, 1.488, 0.343, 6.467, options 1, 2, 3 at 10:30, 11:45 for $1,234.56, "
        "1,250,000 customers on 1.15.2024 call 555-212-4367, 8. "
    )
    text = (chunk * (200_000 // len(chunk) + 1))[:200_000]
    start = time.perf_counter()
    redacted, counts = redact(text)
    assert time.perf_counter() - start < 0.5
    assert "0-3-4-3" not in redacted and "1.488" not in redacted
    assert counts["CARD"] > 0 and counts["SSN"] > 0 and counts["PHONE"] > 0
    # Degenerate inputs guard against super-linear blowup, not raw speed: tens of thousands
    # of one-digit groups in a single run take ~0.35 s locally and longer on a shared CI
    # runner, while anything quadratic would take minutes.
    for bad in (
        "1, " * 60_000,
        "1." * 100_000,
        "1,2" * 60_000,
        "12, x " * 30_000,
        "1-1-11, " * 25_000,
        "1 ,  " * 40_000,
        "1,   ,   " * 20_000,
        "1,000," * 30_000,
        "9.99, " * 30_000,
        "12345 " * 30_000,
        "1 12345 " * 25_000,
    ):
        start = time.perf_counter()
        redact(bad)
        assert time.perf_counter() - start < 2.0, bad[:12]
