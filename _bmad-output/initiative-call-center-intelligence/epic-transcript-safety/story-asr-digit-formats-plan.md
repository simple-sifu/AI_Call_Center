---
title: 'ASR digit formats'
type: 'feature'
ticket: '7'
created: '2026-10-12'
status: done
baseline_revision: '4477214e2a0ec15ef42c9431e0e60d3e015af641'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The tiny Whisper model often writes a number read aloud as digit groups split by commas, dots, or hyphen fragments. Redaction treats a comma or dot as the end of a number, so these pass in clear. Real outputs from `say` probes (2026-10-12): "4-5-39, 1-48-8, 0-3-4-3, 6-4-6-7.", "5 4 2 5, 2 3 3 4, 3 0 1 0, 9 9 0 3.", "4.539, 1.488, 0.343, 6.467.", and an SSN as "1, 2, 3, 4, 5, 6, 7, 8, 9." All came out with counts 0.

**Approach:** After the written (3.3) and spoken (3.4) passes, find dictated digit runs in what is left: short digit groups joined by commas, dots, hyphens, parentheses or spaces. Redact a run whole when it holds 7 or more digits, labelled by digit count as in 3.4.

## Boundaries & Constraints

**Always:**
- A dictated run is a maximal sequence of 2 or more plain digit groups of 1–4 digits each. Groups are joined by up to 3 separator characters from `,` `.` `-` `(` `)` and whitespace, or by a segment join (renegotiated 2026-10-12 after implementation: no comma or dot is required, so hyphen fragments such as "1-2-3-4-5-6-7-8-9" and space groups such as "555 1234" count; parentheses added). Only digits that 3.3 and 3.4 left unredacted can form a run. A redacted value that covers a closing parenthesis also covers its matching opening one. "Plain" excludes (renegotiated 2026-10-12 after review pass 1): amounts only when marked by a currency sign (`$19.99`); times (`10:30`); dates only with a 4-digit year (`1-15-1980`, `2024-01-15`, `1/15/2024`, `1.15.2024`, month 1–12 and day 1–31), and a date always ends a run whatever joins it; digits glued to letters (`UA123`); and a comma-thousands number (`1,250,000`: 1–3 digits, then `,ddd` groups with no spaces), which ends a run. Shapes like `4-5-39` or `1-23-45` (no 4-digit year) and bare decimals (`6467.5`, `8.9`) are ordinary digit groups. When a redacted run is joined (by a run separator) to a digit group of 5 or more digits, the placeholder also covers that group, so a number is never cut. Accepted cost: bare decimal lists such as "rates 1.25, 2.50, 3.75" are redacted.
- A dictated run with 7 or more digits in all is redacted whole: 9 digits `[SSN]`, 12 or more `[CARD]`, otherwise `[PHONE]`. No Luhn check, because ASR mishears digits. Shorter runs are kept. Accepted cost (user's decision, 2026-10-12): a comma list of short numbers with 7+ digits in all is redacted ("rooms 101, 102, 103" → "rooms [SSN]", "1, 2, 3, 4, 5, 6, 7" → "[PHONE]").
- The pass runs last, over the text with emails, written values and spoken values masked, so every 3.3 and 3.4 result is unchanged.
- Placeholder, segment, and audit rules as in 3.3. Every quantifier is bounded, and timing: realistic 200 KB text under 0.5 s; degenerate inputs (tens of thousands of tiny groups in one run, including the 3.3 loop) under 2.0 s, which still catches super-linear blowup (user's decision, 2026-10-12, as for the story 3.4 timing fix).

**Never:** new PII types; changing 3.3/3.4 results for text they already redact; redacting a run that 3.3 protects as one number (13–19 unbroken digits, or 4-4-4-4, 4-4-4-4-d, 4-6-5 groups joined only by spaces or hyphens, such as a Luhn-failing 16-digit reference); other short-group runs 3.3 or 3.4 kept may now be redacted; `models.py`, `state.py`, `graph.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Real ASR card forms | the four probe outputs above | each value → `[CARD]` (`[SSN]` for the SSN), counts 1 | No error expected |
| Comma and dot groups | "4539, 1488, 0343, 6467", "555, 212, 4367", "123. 45. 6789", "555-212, 4367" | `[CARD]`, `[PHONE]`, `[SSN]`, `[PHONE]` | — |
| Split across segments | A "card 4 5 3 9, 1 4 8 8," B "0 3 4 3, 6 4 6 7 ok" | A "card [CARD]", B " ok" | — |
| Short lists kept | "options 1, 2, 3", "rooms 4.5, 6", "pick 1, 2, or 3" | unchanged | — |
| Long lists (accepted cost) | "rooms 101, 102, 103", "1, 2, 3, 4, 5, 6, 7", "page 12 13 14 15", "in 2019, 2020 and 2021" | "rooms [SSN]", "[PHONE]", "page [PHONE]", "in [PHONE] and 2021" | — |
| Hyphen and space fragments | "It's 1-2-3-4-5-6-7-8-9", A "my social is 1-2-3" + B "4-5-6-7-8-9 thanks", "call 555 1234 today", "(555), 212, 4367" | "It's [SSN]", A "my social is [SSN]" + B " thanks", "call [PHONE] today", "[PHONE]" | — |
| Formatted numbers kept | "$1,234.56", "1,250,000 customers", "on 1.15.2024", "at 10:30, 11:45", "Due 2024-01-15, 1234", "dob 1-15-1980, 1234", "on 1.15.2024. 3 4 5" | unchanged | — |
| Review pass 1 leaks | "ssn 1-23-45 6789", "ssn 1-23-45 6-7-8-9", "ssn 1.2.3.4.5.6.7.8.9", "ssn 1, 2, 3, 4, 5, 6, 7, 8.9", "card 4539, 1488, 0343, 6467.5", "4.539, 1.488, 0.343, 6.46" | "ssn [SSN]" ×4, "card [CARD]", "[CARD]" | — |
| Never cut by a long group | "acct 1234-567-89012", "ref 12345-1234-567", "order 98765 4321 123" | "acct [CARD]", "ref [CARD]", "order [CARD]" | — |
| After a written value | "555-212-4367, 8", "my SSN is 123-45-6789, 12" | "[PHONE], 8", "my SSN is [SSN], 12" (written value as in 3.3; the short rest is kept) | — |
| 3.3/3.4 unchanged | the existing 3.3 and 3.4 suites | pass unchanged, except four 3.3 cases now redacted whole (user's decision, 2026-10-12): "ref 123-45- 6789" → "ref [SSN]", "1234-5678", "0123-45-6789", "5555-123-4567" → "[PHONE]" | — |

</frozen-after-approval>

## Code Map

- `src/call_center/pii.py` -- `_find` (emails → `_digit_spans` written pass → mask → `_spoken_pass`); add the dictated pass after the spoken pass on the fully masked text, and merge its spans as `_find` does today. Reuse `_leftover_kind`-style labelling (9 SSN, 12+ CARD, else PHONE), `_mask`, and the join handling (`_mark_joins`, `_JOIN`). Keep the module docstring current.
- `src/call_center/spoken_numbers.py` -- `_OTHER_PATTERN` classifies amounts, times, dates and glued digits; reuse it (or extract a shared helper) so "plain" means the same in both passes.
- `src/call_center/stages/pii_redaction.py` -- unchanged; counts flow through `redact_segments`.
- `tests/unit/test_pii.py` -- 3.3/3.4 suites, property tests (seeds 3303–3312), timing tests; must pass unchanged. Add new tests beside them.
- `tests/fixtures/make_call.py` -- named calls (story 3.5); add a `dictation` call. Running with no names skips `default`.
- `tests/security/test_end_to_end.py`, `tests/security/llm_guard.py` -- slow real-audio tests and the guard (`assert_redacted_only(card)`); add the dictation call there.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/pii.py` -- the dictated pass.
- [x] `tests/unit/test_pii.py` -- every matrix row, with the probe outputs verbatim; a seeded property test (at least 2,000 cases) of random cards, SSNs and phones written with random comma/dot/hyphen/space groupings, fragments and segment splits, expecting exact output; a benign list of short lists, amounts, dates, times and formatted numbers that stay unchanged; timing.
- [x] `tests/fixtures/make_call.py` and `tests/fixtures/call_dictation.wav` -- a stereo call (under 1 MB) where the customer reads the test card as "Four five three nine. One four eight eight. Zero three four three. Six four six seven." and an SSN as "one two three, four five, six seven eight nine".
- [x] `tests/security/test_end_to_end.py` -- slow test: the dictation call completes, the guard passes, and neither the card's nor the SSN's digits reach an LLM stage.

**Acceptance Criteria:**
- Given `HF_HUB_OFFLINE=1 uv run pytest -m slow`, when it runs, then the dictation call's redacted transcript holds no card or SSN digits.
- Given the 3.3 and 3.4 test suites, when they run, then every existing test passes unchanged except the four 3.3 cases in the matrix, whose expectations become whole-run redaction.

## Implementation Notes

- `pii._dictated_pass` runs last in `_find`, over `work` with emails, written, spoken and absorbed spans masked, and with the runs 3.3 protects as one number masked too (`_digit_spans` appends them to an optional `protected` list). `_mask` tolerates overlapping spans; the overlap/paren loop is the `_disjoint` helper. Labels reuse `_kind_by_digits` (renamed from `_spoken_kind`).
- Current rule (after review pass 1): 2+ plain groups of 1-4 digits joined by up to 3 characters from `,` `.` `-` `(` `)` and whitespace (segment join spaces not counted). Not plain, ending a run (`_DICTATION_TOKEN` in `pii`): currency-marked amounts, times, dates with a 4-digit year (`_valid_date`: month 1-12, day 1-31, either order when the year is last; an invalid one is read as its groups), comma-thousands numbers, glued digits. 2-digit-year shapes (`4-5-39`) and bare decimals (`6467.5`) are plain groups. Runs and 5+ digit stretches joined end to end by run separators form a chain (review pass 2); when any run in it has 2+ groups and 7+ digits, the whole chain is one placeholder labelled by all its digits (9 SSN, 12+ CARD, else PHONE), counted once, so a stretch is never claimed twice and a short run beside a stretch is never left in clear. A placeholder also takes a matching opening parenthesis. A comma-thousands number never starts right after a digit or a digit then `.`/`,` (`4.539,148,803` -> `[PHONE]`).
- `spoken_numbers` is back to its own `_OTHER_PATTERN`; only `glued` is public and shared.
- Accepted-cost examples tested: `rooms 101, 102, 103`, `page 12 13 14 15`, `in 2019, 2020 and 2021` -> `in [PHONE] and 2021`, `rates 1.25, 2.50, 3.75` -> `rates [SSN]`. Known kept: `123,456,789` (comma-thousands).
- Tests: four 3.3 cases now expect whole-run redaction (`test_hyphen_space_inside_a_segment_is_not_a_written_separator`, `test_digit_matches_never_cut_a_longer_run_of_short_groups`), and `_expected_spans` calls `pii._digit_spans`. The dictated property test (seed 3313, 3,000 cases) covers mixed, hyphen-only and space-only groupings with segment splits, 2-digit-year date-like shapes and trailing decimals; it skips only renderings that 3.3 would take or protect, or that hold a non-plain token (currency amount, time, 4-digit-year date, thousands, 5+ digits). Degenerate-input timing loops use a 2.0 s ceiling (as in 3.4); realistic 200 KB texts keep 0.5 s.
- `LLMGuard.assert_redacted_only(*values)` checks several digit values. The dictation call transcribes as card `4-5-3-9` / `1-488` / `0-3-4-3` / `6-4-6-7` (3.3 card across segments) and SSN `1-2-3` / `4-5-6-7-8-9` (dictated pass). The SSN slow test asserts `[SSN]` and `[CARD]`, audit `SSN 1, CARD 1`, and no 3-digit in-order stretch of the SSN or any card group (digits or number words).

## Plan Change Log

- 2026-10-12 (user's decision after review pass 2): degenerate timing inputs, including the existing 3.3 loop, have a 2.0 s ceiling; realistic 200 KB text keeps 0.5 s.

- 2026-10-12 (human renegotiation after review pass 1): dates need a 4-digit year and always end a run; only currency-marked amounts are excluded; a redacted run extends over joined 5+ digit groups. Wrong results this fixes (before the change): "Due 2024-01-15, 1234" → "Due [CARD]", "ssn 1-23-45 6789" kept, "ssn 1.2.3.4.5.6.7.8.9" → "ssn [PHONE].8.9", "acct 1234-567-89012" → "acct [PHONE]-89012".

- 2026-10-12 (user's decision): four 3.3 "never cut a longer run" cases ("ref 123-45- 6789", "1234-5678", "0123-45-6789", "5555-123-4567") now expect whole-run redaction; the run is still never cut. The 3.4 property-test helper `_expected_spans` calls `pii._digit_spans` (the 3.3 pass the spoken pass uses) instead of `pii._find`; no behaviour change.

- 2026-10-12 (human renegotiation after implementation): the real dictation call gave the SSN as hyphen fragments across two segments ("1-2-3" / "4-5-6-7-8-9"), which the comma-or-dot requirement left in clear. Requirement dropped; parentheses are separators. The SSN slow test must pass, not xfail.

## Review Triage Log

Pass 1 (quick lens): high 3, medium 4, low 2, false 0, maybe-false 1. All reproduced except the flaky slow test.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | date handling | high | intent_gap (renegotiated) | "Due 2024-01-15, 1234" → "Due [CARD]"; "ssn 1-23-45 6789" kept. Dates need a 4-digit year and always end a run. |
| 2 | decimal at end of run | high | intent_gap (renegotiated) | "ssn 1.2.3.4.5.6.7.8.9" → "ssn [PHONE].8.9". Only currency-marked amounts excluded. |
| 3 | 5+ digit group cuts a run | high | intent_gap (renegotiated) | "acct 1234-567-89012" → "acct [PHONE]-89012". Placeholder extends over joined long groups. |
| 4 | SSN slow test can't see partial leaks | medium | patch | "1-2-3 [SSN]" passed. Asserts `[SSN]`, audit, and no 3-digit SSN stretch. |
| 5 | fixture docstring | medium | patch | Described comma/dot forms the model does not write. Corrected. |
| 6 | tickets.toml entry 7 stale | medium | patch | Updated description and verify. |
| 7 | 3.3 timing loop near limit | medium | intent_gap (user chose 2.0 s for degenerate inputs) | "1 " * 100_000 0.43 s locally. |
| 8 | dead `kinds` code | low | patch | Removed. |
| 9 | flaky card slow test | maybe-false | defer | Failed once in 7 full runs, not reproduced; would be medium if real. |

Pass 2 (quick lens, after patches): high 2, medium 2, false 0. All reproduced.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | long stretch claimed twice | medium | patch | "1234-567-89012-345-6789" → "[CARD][CARD]", CARD 2. Chains of runs and long stretches are one value. |
| 2 | short run beside a long stretch left in clear | high | patch | "12-345-67890 1234 567" → "12-345-[CARD]". Same chain fix. |
| 3 | thousands after a decimal point | high | patch | "4.539,148,803" kept. Lookbehind fixed. |
| 4 | 3.3 timing ceiling changed without renegotiation | medium | intent_gap (user chose 2.0 s) | Recorded above. |

After patches: `uv run pytest` 933 passed; `HF_HUB_OFFLINE=1 uv run pytest -m slow` 13 passed; ruff clean.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
