"""Typed value models carried in the pipeline state.

Every stage reads and writes these shapes. They are frozen and reject unknown fields,
except ``QAScores``, which ignores extra keys so an LLM-supplied ``overall`` is dropped.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    computed_field,
    field_validator,
    model_validator,
)

_STRICT = ConfigDict(frozen=True, extra="forbid")

RunStatus = Literal["running", "completed", "blocked", "failed"]
AuditOutcome = Literal["ok", "blocked", "failed"]
Sentiment = Literal["negative", "neutral", "positive"]

QA_WEIGHTS: dict[str, float] = {
    "professionalism": 0.15,
    "empathy": 0.20,
    "resolution": 0.30,
    "compliance": 0.20,
    "clarity": 0.15,
}


class TranscriptSegment(BaseModel):
    model_config = _STRICT

    speaker: str = Field(min_length=1)
    start: float = Field(ge=0, allow_inf_nan=False, description="seconds from start of audio")
    end: float = Field(ge=0, allow_inf_nan=False, description="seconds from start of audio")
    text: str

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "TranscriptSegment":
        if self.end < self.start:
            raise ValueError("segment end must not be before start")
        return self


class Transcript(BaseModel):
    """Used for both the raw ``transcript`` and the ``redacted_transcript``."""

    model_config = _STRICT

    segments: tuple[TranscriptSegment, ...]
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Entity(BaseModel):
    model_config = _STRICT

    text: str = Field(min_length=1)
    type: str = Field(min_length=1)


class SentimentTrajectory(BaseModel):
    """Exactly three phases, in order: opening, middle, closing."""

    model_config = _STRICT

    opening: Sentiment
    middle: Sentiment
    closing: Sentiment


class Summary(BaseModel):
    model_config = _STRICT

    call_purpose: str = Field(min_length=1)
    action_items: tuple[str, ...]
    sentiment_trajectory: SentimentTrajectory
    entities: tuple[Entity, ...]


class DimensionScore(BaseModel):
    model_config = _STRICT

    score: StrictInt = Field(ge=1, le=10)
    rationale: str


class QAScores(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    professionalism: DimensionScore
    empathy: DimensionScore
    resolution: DimensionScore
    compliance: DimensionScore
    clarity: DimensionScore

    @computed_field
    @property
    def overall(self) -> float:
        """Weighted mean of the dimension scores x 10, rounded to 1 decimal (10.0-100.0)."""
        total = sum(weight * getattr(self, dim).score for dim, weight in QA_WEIGHTS.items())
        return round(total * 10, 1)


class AuditEvent(BaseModel):
    model_config = _STRICT

    stage: str = Field(min_length=1)
    at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    outcome: AuditOutcome
    detail: str = ""

    @field_validator("at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
