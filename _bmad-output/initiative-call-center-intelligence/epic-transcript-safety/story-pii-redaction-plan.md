---
title: 'PII redaction'
type: 'feature'
ticket: '3'
created: '2026-10-11'
status: 'built'
baseline_revision: '5997eee6ceb4cc3ca36bfce31c3f459cb3eda991'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 3
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The redaction stage is a stub that blanks every segment to `[REDACTED]`, so once Epic 4 lands the LLM stages would either see nothing useful or, with the stub removed, see raw SSNs, card numbers, emails, and phone numbers.

**Approach:** Add a redaction module that finds SSN, card (Luhn-checked), email, and phone values written as digits and replaces each with `[SSN]`, `[CARD]`, `[EMAIL]`, or `[PHONE]`. The stage keeps every segment's speaker and timing and audits counts by type, never values.

## Boundaries & Constraints

**Always:**
- Detection runs on the segments joined with a space (as injection detection does), so a value split across two segments is still redacted. A match that crosses a boundary puts the placeholder in the segment where it starts and removes the rest from the following segment(s).
- Card: within any run of digit groups joined by single spaces or hyphens (including runs that span segments), every 13–19 digit stretch that starts and ends on a group boundary and passes Luhn → `[CARD]`; the rest of the run is still checked for SSN and phone. So a card next to a CVV or a stray digit is still redacted.
- Only a run that looks like one number is protected (left wholly untouched, no SSN or phone match inside it) when it fails Luhn: 13–19 unbroken digits, or card-style groups (`dddd dddd dddd dddd`, with an optional final group of 1–3 digits; or `dddd dddddd ddddd`). Any other run is checked for SSN and phone piece by piece.
- Emails (written and spoken) are found before cards, so digits inside an address cannot break it up.
- SSN: `ddd-dd-dddd` or `ddd dd dddd`. Phone (North American): 10 digits as `(ddd) ddd-dddd`, `ddd-ddd-dddd`, `ddd.ddd.dddd`, `ddd ddd dddd` or bare, with an optional `+1`/`1` prefix; also 7-digit `ddd-dddd`. Email: `local@domain.tld`.
- Digit matches never start or end inside a longer digit run.
- All text other than the replaced values is byte-identical, including whitespace and punctuation. A transcript with no PII comes back equal to the input.
- Audit detail: `redacted SSN 1, CARD 0, EMAIL 2, PHONE 1`; outcome `ok`.
- A missing transcript gives an empty redacted transcript, as the stub does.

**Decisions (user, 2026-10-11):**
- The card rule above replaces "a 13–19 digit run failing Luhn is left wholly untouched" after review pass 1 showed adjacent values leaking (user: "replace card rule and rebuild").
- Spoken-style emails are redacted too: `<word> at <word> dot <tld>` for the TLDs com, net, org, edu, gov, io, co, us, uk, ca (multi-dot domains such as "dot co dot uk" included) → `[EMAIL]`.
- A bare 9-digit number (not part of a longer digit run) is redacted as `[SSN]`, erring toward privacy.

**Never:** spoken number words (3.4); names, addresses, dates of birth, account numbers; values in the audit or logs; changing `models.py`, `state.py`, `graph.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SSN | "my social is 123-45-6789." | "my social is [SSN]." | No error expected |
| Card | "card 4111 1111 1111 1111 thanks" | "card [CARD] thanks" | — |
| Card fails Luhn | "ref 1234 5678 9012 3456" | unchanged | — |
| Email | "it's jane.doe+x@example.co.uk" | "it's [EMAIL]" | — |
| Spoken email | "jane doe at gmail dot com" | "jane [EMAIL]" or "[EMAIL]" (the local part is at least the word before "at") | — |
| Bare 9 digits | "it's 123456789" | "it's [SSN]" | — |
| Phone forms | "(555) 123-4567", "555.123.4567", "+1 555 123 4567", "555-0199" | each → `[PHONE]` | — |
| Adjacent values | "ssn 123-45-6789 555-123-4567", "call 555-123-4567 555-0199" | "ssn [SSN] [PHONE]", "call [PHONE] [PHONE]" | — |
| Card with CVV | "card 4111 1111 1111 1111 123" | "card [CARD] 123" | — |
| Digit in previous segment | segment A "Option 2", segment B "4111 1111 1111 1111" | A unchanged, B "[CARD]" | — |
| Digits in an email | "john.1234567890123@gmail.com" | "[EMAIL]" | — |
| Split value | segment A "card is 4111 1111", segment B "1111 1111 ok" | A "card is [CARD]", B " ok" (or "ok"); timing kept | — |
| Clean text | "I'll call you back in 5 minutes, order 42." | unchanged | — |
| Mixed | one segment with all four types | four placeholders; audit counts 1 each | — |
| Audit hygiene | any redaction | no value or fragment of one in the audit detail | — |

</frozen-after-approval>

## Code Map

- `src/call_center/stages/pii_redaction.py` -- stub; replace `run`, keep `NAME`, `_PLACEHOLDER`, and the `stages_completed` entry.
- `src/call_center/stages/injection_detection.py` -- the join-with-a-space precedent and audit style to mirror.
- `src/call_center/models.py` -- `Transcript(segments, audio_sha256)`, `TranscriptSegment(speaker, start, end, text)`; frozen, so build new segments. Read only.
- `src/call_center/injection.py` -- module style (docstring, bounded quantifiers, module constants) to match.
- `tests/security/test_blocked_run.py:81` -- `test_pii_redaction_masks_text_and_keeps_timing` asserts the stub's `[REDACTED]`; update it to a real SSN/timing case. The rest of the file stays.
- `tests/security/test_stage_order.py` -- already guards stage order; no change.
- `/private/tmp/claude-501/-Users-tommyhan-projects-AI-Call-Center/ce487c08-df0f-47e7-a952-9ad002f937cf/scratchpad/story33-attempt3.patch` -- attempt 3 (reverted; the base to rebuild from, see Plan Change Log). `/private/tmp/claude-501/-Users-tommyhan-projects-AI-Call-Center/ce487c08-df0f-47e7-a952-9ad002f937cf/scratchpad/story33-attempt2.patch` -- attempt 2 (reverted). `/private/tmp/claude-501/-Users-tommyhan-projects-AI-Call-Center/ce487c08-df0f-47e7-a952-9ad002f937cf/scratchpad/story33-attempt1.patch` -- attempt 1 (reverted): `src/call_center/pii.py`, the stage, `tests/unit/test_pii.py`, `tests/integration/test_pii_pipeline.py`, the `test_blocked_run.py` change. Reuse it, changing the card rule and pass order; `test_card_failing_luhn_is_untouched`'s "ref 555 123 4567 1234" case asserted the leak and must change to `[PHONE] 1234`.

## Tasks & Acceptance

**Execution:**
- [x] `src/call_center/pii.py` -- `redact(text) -> (text, counts)` plus a segment-aware `redact_segments(texts) -> (texts, counts)` over the joined text; emails first, then SSN/phone candidates, then cards (Luhn windows inside digit-group runs that respect the SSN/phone candidates; protected only for one-number-shaped runs), then SSN/phone claim what cards left.
- [x] `src/call_center/stages/pii_redaction.py` -- redact the transcript's segments, rebuild them with the same speaker and timing, audit counts.
- [x] `tests/unit/test_pii.py` -- every matrix row; Luhn helper cases; a regression list of benign phrases (times, prices, order numbers, years, 4-digit PINs, zip codes) that stay unchanged; 200 KB scan under 0.5 s; seeded random property tests (fixed seed, at least 2,000 cases each, random valid cards, SSNs and phones, never hand-picked values): (1) adjacent SSN/phone pairs in every written form; (2) a random valid card with a random 1–4 digit group before it and/or after it; (3) an SSN or phone followed by a random 1–6 digit group; (4) every value form in a segment after a previous segment ending in a word, a digit, `d-`, `1`, or `1-`. Each asserts the exact output: every value's digits gone, the right label, and the neighbouring text byte-identical.
- [x] `tests/security/test_blocked_run.py` -- replace the stub assertion with a real redaction that keeps speaker and timing.

**Acceptance Criteria:**
- Given seeded transcripts with all four types, when the pipeline runs with a fake transcriber, then no seeded value appears anywhere in `redacted_transcript` or the audit trail.
- Given a fixture call (`call_stereo.wav`, `call_mono.wav`), when it runs through the real pipeline, then its redacted text equals its transcript text.

## Implementation Notes

- Pass order: card (Luhn pass redacted, fail protected), then written email, spoken email, SSN, phone. Emails run before the digit patterns so digits inside an address cannot split it. Later passes run on a masked working copy so offsets stay aligned.
- "Digit run" for SSN/phone boundaries means digits joined directly or by a hyphen or dot; a space ends the run (so two space-separated phones are both redacted). Card candidates use digits joined by single spaces or hyphens, taken only as a whole 13-19 digit run.
- Added `tests/integration/test_pii_pipeline.py` for the two acceptance criteria (seeded fake-transcriber run; slow fixture-call equality).
- Attempt 2 (after review pass 1 and the user's card-rule change): rebuild from the attempt-1 patch. The first two notes above describe attempt 1 and are superseded: pass order is now written email, spoken email, card, SSN, phone; cards are Luhn-valid stretches on group boundaries inside a run (longest at each start, leftmost first), found with mod-10 prefix sums; protected shapes accept a space or a hyphen between groups.
- Attempt 3 (after review pass 2): rebuilt from the attempt-2 patch with SSN/phone candidates found before cards and the window acceptance rule. The hyphen-at-segment-end join also applies to cards (`["card 4111-1111-", "1111-1111"]` → `["card [CARD]", ""]`), from the frozen split-value rule. Known gaps: a split at a dot or parenthesis is not joined; a card with a hyphenated CVV gives `[CARD]-123`. Property test: seed 3303, 3,000 cases.
- Attempt 4 (after review pass 3): rebuilt from the attempt-3 patch per the Design Notes. The join space is kept and marked in the working copy (same length, so no offset mapping); patterns accept a hyphen plus the marker as one separator, and the marker ends a digit run like a space. The join marker also covers a hyphen that starts the next segment (`["ssn 123-45", "-6789"]` -> `["ssn [SSN]", ""]`). Every card window, shaped or not, is refused when it overlaps any SSN/phone candidate. Known gap, accepted: a hyphenated stray group glued to a card's first group (`x 034-6536 329989 72483`) is taken as a 7-digit phone, so the rest of that card stays in clear. Refinement found by the property tests: when a same-rank window overlaps a chosen one and covers groups nothing claimed (a 4-digit group beside a 4-4-4-4 card, about 10% of such cases), the readings are merged into one `[CARD]` (over-redacts that group or a 4-digit CVV) rather than leaving card digits visible; two adjacent cards still get two labels. Property tests: seeds 3304-3309, 3,000-4,000 cases each (also run locally with six other seeds at 20,000 cases).

## Plan Change Log

- Review pass 3 (iteration 3), bad_plan. Trigger: window choice was "longest, leftmost", and a window could contain one SSN/phone candidate. Results: "Option 2" + a random valid card left the card's last group visible about 9% of the time; "call 555-123-4567 1000" → "call [CARD]"; a CVV was swallowed into the card about 11% of the time; and dropping the join space at a `d-` join leaked complete values (["dial 1-", "555-0199"] unchanged). Every earlier test used hand-picked values that happened to pass. Amended: Design Notes (no overlap with candidates; card-shape-first window choice; join space kept, hyphen join only adds matches) and Tasks (four random property tests with exact expected output). Known-bad state avoided: any rule verified only on fixed example values. KEEP: everything attempt 3 kept, its join-prefix handling, the pass-2 cases, and every matrix-row test.
- Review pass 2 (iteration 2), bad_plan. Trigger: card windows were searched before SSN/phone and could start or end inside a hyphen-joined SSN or phone, breaking the frozen rule "digit matches never start or end inside a longer digit run": "call 634-11-1263 288-857-1938 ok" → "call 634-11-[CARD] ok" (about a third of random adjacent pairs mislabelled, a quarter leaving digits). Also folded in: the "Press 1" + phone prefix landing in the earlier segment, and hyphen-split values across segments. Amended: Tasks (pass order, property test) and Design Notes (window acceptance rule, join handling). Known-bad state avoided: any card window that cuts an SSN/phone candidate. KEEP: attempt 2's email-first order, digit-run splitting, protected one-number shapes, prefix-sum Luhn windows, segment mapping and masking, bounded regexes, the stage and audit format, and every existing test except that the adjacency tests must not rely on lucky Luhn-failing values.

## Review Triage Log

Pass 1 (quick lens): high 2, medium 1, low 1, false 0, maybe-false 0. Every claim reproduced with `redact` / `redact_segments`.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `_CARD` protection, adjacent values | high | intent_gap | "call 555-123-4567 555-0199" and "ssn 123-45-6789 555-123-4567" leak unchanged: the two values form one 13-19 digit run, fail Luhn, and are protected. Root cause is the frozen rule "a run of 13-19 digits failing Luhn is left wholly untouched". |
| 2 | `redact_segments`, neighbouring segments | high | intent_gap (same root as 1) | ["Option 2", "4111 1111 1111 1111"] leaves a valid card: the join makes a 17-digit run that fails Luhn. |
| 3 | `_CARD` whole run only | high | intent_gap (same root as 1) | "card 4111 1111 1111 1111 123" (card plus CVV) leaves the card in clear. |
| 4 | pass order, card before email | medium | intent_gap (folded in; Tasks order) | "john.1234567890123@gmail.com" leaks: the 13 digits are protected before the email pass. |
| 5 | `_SPOKEN_EMAIL` look-alikes | low | reject | "look at that dot com bubble" → "[EMAIL] bubble". Over-redaction in the safe direction, from the shape the user chose; rare in calls. |
| 6 | tests miss adjacency | — | intent_gap (same root as 1) | No test puts values next to each other or across segments; one test asserts the leak. |

Code reverted to baseline; attempt 1 saved outside the repo as a reference patch. User replaced the card rule (2026-10-11); plan updated and rebuilt.

Pass 2 (quick lens, attempt 2): high 1, medium 2, low 1, false 0, maybe-false 0. All reproduced.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `_card_windows` vs SSN/phone | high | bad_plan | "call 634-11-1263 288-857-1938 ok" → "call 634-11-[CARD] ok"; "call 912-656-5363 938-434-2674 ok" → "call [CARD]-2674 ok"; "x 123-45-6789 123-45-6789" → "x [CARD]". Card windows cut hyphen-joined values. |
| 2 | `_PHONE` prefix across segments | medium | bad_plan (folded) | ["Press 1", "555 123 4567"] → ["Press [PHONE]", ""]: the "1" is eaten and the placeholder moves to the other segment. |
| 3 | hyphen at a segment end | medium | bad_plan (folded) | ["my ssn", "is 123-45-", "6789"] unchanged, counts 0, against "a value split across two segments is still redacted". |
| 4 | seeded tests | low | bad_plan (folded) | Adjacency test used values that happen to fail Luhn; replaced by a property test in Tasks. |

Code reverted to baseline again; attempt 2 saved outside the repo as a reference patch.

Pass 3 (quick lens, attempt 3): high 2, medium 1, low 1, false 0, maybe-false 0. All reproduced.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `_card_windows`, stray group before a card | high | bad_plan | ["Option 2", "4804 0576 5019 6405"] → ["Option [CARD]", " 6405"]: four card digits visible (1,792 in 20,000 random cards). |
| 2 | `_join_hyphens` drops the join space | high | bad_plan (folded) | ["dial 1-", "555-0199"], ["room 4-", "123-45-6789"] unchanged, counts 0; the same text in one segment is redacted. |
| 3 | `_window_check`, candidate plus a short number | medium | bad_plan (folded) | "call 555-123-4567 1000" → "call [CARD]": wrong label, and the non-PII "1000" removed. |
| 4 | longest window swallows a CVV | low | bad_plan (folded) | 2,142 in 20,000 random cards + a 1–3 digit group gave "card [CARD] ok"; nothing leaks. |

Code reverted to baseline again; attempt 3 saved outside the repo as a reference patch.

Pass 4 (quick lens, attempt 4): high 1, medium 1, low 0, false 0, maybe-false 0. Both reproduced.

| # | Location | Verdict | Route | Evidence / action |
|---|---|---|---|---|
| 1 | `_window_check` shaped-window exemption | high | patch | ["call 863-47-7161", "8208 5357 1678 2626 ok"] → ["call 863-47-[CARD]", " ok"]; caused by the implementer's deviation from the Design Notes. Fix: remove the exemption (no card window may overlap a candidate) and add an SSN/phone-then-card property test. |
| 2 | `_mark_joins`, next segment starts with a hyphen | medium | patch | ["ssn 123-45", "-6789"] unchanged; ["call 555", "-123-4567"] → ["call 555", "-[PHONE]"]. Fix: also join digit + `-digit`. Split inside a digit group (["123-45-67", "89"]) deferred to deferred-work.md (user chose a, 2026-10-11). |

## Design Notes

Order: emails (masked), then find SSN and phone candidates, then cards, then claim the SSN/phone candidates cards did not take.

- A card window (13–19 digits on group boundaries, Luhn-valid) is accepted only if it does not overlap any SSN/phone candidate at all. A card-shaped window cannot contain one (its groups are 4 digits or more), so real cards are unaffected; a phone or SSN next to a short number therefore stays `[PHONE]`/`[SSN]` plus the number.
- Choosing among the Luhn-valid windows of a run: prefer card-shaped windows (`4-4-4-4`, `4-6-5`, `4-4-4-4-3`, or one unbroken group), then 16 digits, then 15, then any length, then leftmost; take the best, then repeat on what is left of the run. So a stray group before a card, or a CVV after it, never joins the card window when the card's own window is valid.
- Known gap, accepted: a card read in odd groups that contain a phone- or SSN-shaped piece (say `411 111 111 1111 111`) is redacted as that piece, leaving the other groups.
- A protected one-number-shaped run is checked after windows, as now.
- Segment joins: a phone's `1`/`+1` prefix never comes from an earlier segment. The join space is always kept. At a join position only, a hyphen followed by the join space also counts as an SSN/phone/card separator, so `123-45-` + `6789` is found. This adds matches and never removes one: a value the plain space-joined text would catch must still be caught (for example `["dial 1-", "555-0199"]` → `["dial 1-", "[PHONE]"]`).

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: fixture calls pass, redacted text equals transcript text
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
