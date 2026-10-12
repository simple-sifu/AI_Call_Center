"""Guard for the LLM-backed stages: records what each one receives.

The ``llm_guard`` fixture wraps the real ``summarization.run`` and ``qa_scoring.run`` (the
module attributes the graph reads when it is built, so install it before ``run_pipeline``)
and calls through. Each call gets a copy of the state that records, and fails, any read of
the raw ``transcript``; the ``redacted_transcript`` it was handed is recorded. After the
run, ``assert_redacted_only`` checks a completed call and ``assert_not_run`` a blocked one.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from call_center import spoken_numbers
from call_center.models import Transcript
from call_center.stages import qa_scoring, summarization

LLM_STAGES = (summarization, qa_scoring)
RAW = "transcript"
_LETTER = re.compile(r"[A-Za-z]")


class _RecordingState(dict):
    """State copy that records, then fails, every way of reading the raw transcript."""

    def __init__(self, state, on_raw_read: Callable[[str], None]):
        super().__init__(state)
        self._on_raw_read = on_raw_read

    def _raw(self, how: str):
        self._on_raw_read(how)
        raise AssertionError(f"LLM stage read the raw transcript ({how})")

    def __getitem__(self, key):
        if key == RAW:
            self._raw("[]")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == RAW:
            self._raw("get")
        return super().get(key, default)

    def pop(self, key, *default):
        if key == RAW:
            self._raw("pop")
        return super().pop(key, *default)

    def setdefault(self, key, default=None):
        if key == RAW:
            self._raw("setdefault")
        return super().setdefault(key, default)

    # Bulk reads go through the methods above or fail outright. Overriding __iter__ also
    # stops dict(state) and {**state} from copying the raw value through the C fast path.
    def __iter__(self):
        return iter(list(super().keys()))

    def items(self):
        return [(k, self[k]) for k in self]

    def values(self):
        return [self[k] for k in self]

    def copy(self):
        return dict(self.items())

    def __or__(self, other):
        return dict(self.items()) | other

    # repr/str/format walk the dict storage directly, so a stage formatting the state into
    # a prompt or log would read the raw transcript unseen.
    def __repr__(self):
        return self._raw("repr") if RAW in self.keys() else super().__repr__()

    def __str__(self):
        return self._raw("str") if RAW in self.keys() else super().__str__()

    def __format__(self, spec):
        return self._raw("format") if RAW in self.keys() else super().__format__(spec)


def card_digit_leaks(text: str, card: str, run: int = 4) -> list[str]:
    """Each ``run``-digit stretch of ``card`` (digits only) that ``text`` still holds, read
    as written digits and number words (``spoken_numbers``: teens, tens, ``double``...),
    with punctuation and spaces ignored (``4.539``, ``4 5 3 9``, ``forty five thirty
    nine``); any other word or a placeholder ends a stretch."""
    pieces = {card[i : i + run] for i in range(len(card) - run + 1)}
    chunks, current, pos = [], [], 0
    for m in spoken_numbers.TOKEN.finditer(text):
        if _LETTER.search(text, pos, m.start()):
            chunks.append("".join(current))
            current = []
        token = m.group(0)
        if m.group("hundred") is not None:
            digits = "00"
        elif m.group("other") is not None or m.group("written") is not None:
            digits = re.sub(r"[^0-9]", "", token)
        else:
            digits = spoken_numbers.word_digits(token) or ""
        current.append(digits)
        pos = m.end()
    chunks.append("".join(current))
    return sorted({p for chunk in chunks for p in pieces if p in chunk})


def transcript_text(transcript: Transcript) -> str:
    return " ".join(segment.text for segment in transcript.segments)


@dataclass
class LLMGuard:
    # Stage name -> the redacted transcript handed to each call of it.
    received: dict[str, list[Transcript | None]] = field(
        default_factory=lambda: {stage.NAME: [] for stage in LLM_STAGES}
    )
    # (stage name, how) for each read of the raw transcript.
    raw_reads: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def install(cls, monkeypatch: pytest.MonkeyPatch) -> "LLMGuard":
        """Wrap whatever ``run`` each LLM stage module has now."""
        guard = cls()
        for stage in LLM_STAGES:
            monkeypatch.setattr(stage, "run", guard._wrap(stage.NAME, stage.run))
        return guard

    def _wrap(self, name: str, real):
        def on_raw_read(how: str) -> None:
            self.raw_reads.append((name, how))

        def run(state):
            self.received[name].append(state.get("redacted_transcript"))
            return real(_RecordingState(state, on_raw_read))

        return run

    def assert_redacted_only(self, *values: str) -> None:
        """Each LLM stage ran once, got a redacted transcript, never read the raw one, and
        got no 4-digit stretch of any of ``values`` (each digits only: a card, an SSN)."""
        assert not self.raw_reads, f"LLM stage read the raw transcript: {self.raw_reads}"
        for name, received in self.received.items():
            assert len(received) == 1, f"{name} ran {len(received)} times"
            [redacted] = received
            assert isinstance(redacted, Transcript), f"{name} got no redacted transcript"
            for value in values:
                leaks = card_digit_leaks(transcript_text(redacted), value)
                assert not leaks, f"{name} got card digits {leaks}: {transcript_text(redacted)!r}"

    def assert_not_run(self) -> None:
        ran = {name: len(calls) for name, calls in self.received.items() if calls}
        assert not ran, f"LLM stages ran for a blocked call: {ran}"
        assert not self.raw_reads


@pytest.fixture
def llm_guard(monkeypatch: pytest.MonkeyPatch) -> LLMGuard:
    return LLMGuard.install(monkeypatch)
