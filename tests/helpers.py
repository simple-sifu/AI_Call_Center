"""Helpers shared by test modules (the tests folder is on sys.path)."""

import copy
import re

from call_center.models import Transcript, TranscriptSegment

# A quantifier with no upper bound (``*``, ``+`` or ``{n,}``) outside a character class.
UNBOUNDED = re.compile(r"(?<!\\)[*+](?![^\[]*\])|\{\d*,\}")

# Number words, kept by hand so the tests check the spoken-number table, not mirror it.
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
# Every number word the spoken pass reads, so none of a value's words can hide.
DIGIT_WORDS = {
    *UNIT_WORDS,
    *ZERO_WORDS,
    *TEEN_WORDS,
    *TENS_WORDS.values(),
    "hundred",
    "double",
    "triple",
}


# The fixed redacted transcript the opt-in live checks send to the real provider.
LIVE_REDACTED = Transcript(
    segments=[
        TranscriptSegment(
            speaker="agent", start=0, end=3, text="Thanks for calling, how can I help?"
        ),
        TranscriptSegment(
            speaker="customer",
            start=3,
            end=9,
            text="My payment with card [CARD] was declined and I need my order shipped today.",
        ),
        TranscriptSegment(
            speaker="agent",
            start=9,
            end=14,
            text="I see the decline. I'll send you a new payment link by email right now.",
        ),
        TranscriptSegment(speaker="customer", start=14, end=16, text="Great, thank you so much."),
    ],
    audio_sha256="0" * 64,
)


class FakeTranscriber:
    """Fake ASR that returns the given raw segments for any file."""

    def __init__(self, segments):
        self.segments = list(segments)

    def transcribe(self, path):
        return self.segments


FAKE_SUMMARY = {
    "call_purpose": "The customer asked why their card payment was declined.",
    "action_items": ["Agent re-sends the payment link."],
    "sentiment_trajectory": {"opening": "negative", "middle": "neutral", "closing": "positive"},
    "entities": [{"text": "[CARD]", "type": "placeholder"}],
}


def _dimension(score: int, rationale: str) -> dict:
    return {"score": score, "rationale": rationale}


# Overall 77.0: 0.15*8 + 0.20*7 + 0.30*9 + 0.20*6 + 0.15*8 = 7.7, x 10.
FAKE_QA_SCORES = {
    "professionalism": _dimension(8, "Polite and composed throughout."),
    "empathy": _dimension(7, "Acknowledged the customer's frustration."),
    "resolution": _dimension(9, "Sent a new payment link and confirmed it arrived."),
    "compliance": _dimension(6, "Gave a name but no recording notice."),
    "clarity": _dimension(8, "Explained the next step clearly."),
}

# What the fake answers, by the name of the schema it was asked for.
FAKE_ANSWERS = {"Summary": FAKE_SUMMARY, "QAScores": FAKE_QA_SCORES}

# Card digits used in persistence tests to prove raw ASR text is not stored.
SAMPLE_RAW_CARD = "4539148803436467"


def sample_persist_report(source_file: str = "/calls/sample.wav"):
    """A completed ``CallReport`` with fake summary/scores for DB unit tests."""
    from call_center.models import AuditEvent, QAScores, Summary, Transcript, TranscriptSegment
    from call_center.reports import REPORT_STAGE, CallReport, build_report

    redacted = Transcript(
        segments=[TranscriptSegment(speaker="agent", start=0, end=1, text="Hi")],
        audio_sha256="c" * 64,
    )
    state = {
        "source_file": source_file,
        "stages_completed": ["intake"],
        "transcript": Transcript(
            segments=[TranscriptSegment(speaker="c", start=0, end=1, text=SAMPLE_RAW_CARD)],
            audio_sha256="d" * 64,
        ),
        "redacted_transcript": redacted,
        "summary": Summary.model_validate(FAKE_SUMMARY),
        "qa_scores": QAScores.model_validate(FAKE_QA_SCORES),
        "audit": [AuditEvent(stage="intake", outcome="ok")],
        "status": "running",
        "status_reason": None,
        "report_output_dir": None,
        "report_json_path": None,
        "report_pdf_path": None,
    }
    base = build_report(state)
    event = AuditEvent(stage=REPORT_STAGE, outcome="ok", detail="wrote /tmp/x.json")
    return CallReport(
        source_file=base.source_file,
        status="completed",
        status_reason=base.status_reason,
        stages_completed=(*base.stages_completed, REPORT_STAGE),
        audit=(*base.audit, event),
        redacted_transcript=base.redacted_transcript,
        summary=base.summary,
        qa_scores=base.qa_scores,
    )


# ``FakeChatModel.output`` default: answer each call by the schema it was asked for.
BY_SCHEMA = object()


def schema_name(schema: object) -> str:
    """The model name of a requested schema: a JSON schema's title or the class name."""
    if isinstance(schema, dict):
        return str(schema.get("title"))
    return getattr(schema, "__name__", repr(schema))


class FakeAnswersExhausted(BaseException):
    """A call past the end of ``FakeChatModel.outputs``. Not an ``Exception``, so the
    helper's catch-all cannot turn it into an ordinary provider error."""


class FakeChatModel:
    """Fake chat model: answers each structured-output call by the schema it was asked for.

    By default a ``Summary`` call gets ``FAKE_SUMMARY`` and a ``QAScores`` call
    ``FAKE_QA_SCORES`` (``answers``, keyed by schema name; set an entry to an answer or an
    exception to change what that schema gets). Set ``output`` to a dict, another value
    or an exception to give that same answer to every call, whatever the schema.
    Set ``outputs`` to a sequence of answers and exceptions to give one per call, in
    order; it overrides ``output`` and ``answers``, and a call past its end fails the test.
    ``calls`` holds the messages of each call, ``schemas`` the requested schemas,
    ``methods`` the requested structured-output methods and ``settings`` the settings
    each factory call received.
    """

    def __init__(self) -> None:
        self.output: object = BY_SCHEMA
        self.outputs: list[object] | None = None
        self.answers: dict[str, object] = {
            name: copy.deepcopy(answer) for name, answer in FAKE_ANSWERS.items()
        }
        self.calls: list[list] = []
        self.schemas: list[object] = []
        self.methods: list[object] = []
        self.settings: list[object] = []
        self.call_schemas: list[str] = []  # the schema name each call was answering
        self._schema: object = None

    def with_structured_output(self, schema, **kwargs):
        self.schemas.append(schema)
        self.methods.append(kwargs.get("method"))
        self._schema = schema
        return self

    def invoke(self, messages, *args, **kwargs):
        self.calls.append(list(messages))
        name = schema_name(self._schema)
        self.call_schemas.append(name)
        if self.outputs is not None:
            index = len(self.calls) - 1
            if index >= len(self.outputs):
                raise FakeAnswersExhausted(f"call {index + 1} has no fake answer")
            answer = self.outputs[index]
        elif self.output is BY_SCHEMA:
            if name not in self.answers:
                raise FakeAnswersExhausted(f"no fake answer for schema {name}")
            answer = self.answers[name]
            if isinstance(answer, dict):
                answer = copy.deepcopy(answer)  # so a stage cannot change the next answer
        else:
            answer = self.output
        if isinstance(answer, BaseException):
            raise answer
        return answer
