"""Read-only views of persisted calls for the Observability tab (Epic 6).

Written at persist time in ``persistence.persist_call_report``; token, cost, and
latency fields stay ``None`` until tracing exposes them to the report stage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from call_center.persistence import CallRow, get_engine


@dataclass(frozen=True)
class ObservabilityRecord:
    """One analyzed call, with the metrics the Observability tab lists."""

    call_id: int
    source_file: str
    status: str
    llm_provider: str
    overall: float | None
    analyzed_at: datetime
    stage_outcomes: dict[str, str]
    llm_prompt_tokens: int | None
    llm_completion_tokens: int | None
    llm_cost_usd: float | None
    pipeline_duration_ms: int | None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def record_from_row(row: CallRow) -> ObservabilityRecord:
    return ObservabilityRecord(
        call_id=row.id,
        source_file=row.source_file,
        status=row.status,
        llm_provider=row.llm_provider,
        overall=row.overall,
        analyzed_at=_as_utc(row.analyzed_at),
        stage_outcomes=json.loads(row.stage_outcomes_json),
        llm_prompt_tokens=row.llm_prompt_tokens,
        llm_completion_tokens=row.llm_completion_tokens,
        llm_cost_usd=row.llm_cost_usd,
        pipeline_duration_ms=row.pipeline_duration_ms,
    )


def list_observability_records(engine=None) -> tuple[ObservabilityRecord, ...]:
    """All persisted calls, newest ``analyzed_at`` first (read-only)."""
    engine = engine or get_engine()
    with Session(engine) as session:
        rows = session.scalars(select(CallRow).order_by(CallRow.analyzed_at.desc())).all()
        return tuple(record_from_row(row) for row in rows)
