---
title: 'Refactor sweep'
type: 'refactor'
ticket: '6'
created: '2026-10-12'
status: 'built'
baseline_revision: '8b5743fa65733d77e942b4d8be32d10e67cfad0e'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 3 left small duplications and leftovers: three copies of a fake transcriber in tests, a duplicated `_text` helper, two hand-kept number-word sets, two identical `UNBOUNDED` regexes, a pass-through `_compile` in `injection.py`, two identical digit-group regexes in `pii.py`, a stale "3.3" comment, function-local imports in `test_pii.py`, and a bounded-pattern test that misses three patterns.

**Approach:** Cleanup with no behaviour change: share the test helpers in a `tests/helpers.py` module, inline `_compile`, drop `_MORE_DIGITS` for `_DIGIT_GROUP`, fix the comment, hoist imports, and complete the bounded-pattern list. Out of scope: the deliberately different date patterns in `pii.py` and `spoken_numbers.py`, the looser `UNBOUNDED` in `test_injection.py`, renaming public names, and the open `deferred-work.md` entries (rule changes or an unverified flaky test, not cleanup).

</frozen-after-approval>

## Implementation Notes

Oneshot: mechanical, about 100 lines, mostly test deduplication.

- New `tests/helpers.py` (the tests folder is on sys.path, as `security.llm_guard` already relies on): `FakeTranscriber`, `UNBOUNDED`, and the hand-kept number-word lists (`UNIT_WORDS`, `ZERO_WORDS`, `TEEN_WORDS`, `TENS_WORDS`, `DIGIT_WORDS`). `FakeTranscriber` is used by `test_injection_pipeline.py`, `test_pii_pipeline.py` and `test_end_to_end.py`; the word lists by `test_pii.py` and `test_pii_pipeline.py`; `UNBOUNDED` by `test_pii.py` and `test_spoken_numbers.py`. `test_transcription.py`'s richer fake and `test_injection.py`'s looser `UNBOUNDED` are left as they are.
- `llm_guard._text` is now public `transcript_text`; `test_end_to_end.py` imports it instead of its own copy.
- `injection.py`: `_compile` inlined as `re.compile`.
- `pii.py`: `_MORE_DIGITS` (identical to `_DIGIT_GROUP`) removed; stale "3.3" comment now names `_digit_spans`.
- `test_pii.py`: function-local imports hoisted; `test_patterns_are_bounded` also checks `_CARD_SHAPE` and `_DATE_SEPARATOR`.
- Before and after: `uv run pytest` 933 passed; slow 13 passed; ruff clean.

## Review Triage Log

Pass 1 (quick lens): low 2, no other findings; all intent items verified.

- low, patch: `test_pii.py` `_plainly_dictated` docstring still said "no run 3.3 protects", the wording fixed in `pii.py`; now names `_digit_spans`. (`_expected_spans` refers to the 3.3 rules on purpose and is left.)
- low, patch: the Implementation Notes overstated which files use which helpers; corrected.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass, same count as before
- `HF_HUB_OFFLINE=1 uv run pytest -m slow` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
