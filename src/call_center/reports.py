"""JSON call reports built from pipeline state (Epic 5).

Reports include the redacted transcript and analysis results only, never the raw
``transcript``.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from call_center.models import AuditEvent, QAScores, RunStatus, Summary, Transcript
from call_center.state import PipelineState

_STRICT = ConfigDict(frozen=True, extra="forbid")


class CallReport(BaseModel):
    """The canonical on-disk JSON shape for one analyzed call."""

    model_config = _STRICT

    source_file: str
    status: RunStatus
    status_reason: str | None
    stages_completed: tuple[str, ...]
    audit: tuple[AuditEvent, ...]
    redacted_transcript: Transcript | None
    summary: Summary | None
    qa_scores: QAScores | None


def status_for_report(state: PipelineState) -> RunStatus:
    """Status recorded in the report; a still-``running`` run becomes ``completed``."""
    status = state.get("status", "running")
    return "completed" if status == "running" else status


def build_report(state: PipelineState) -> CallReport:
    """Build a report from ``state`` without reading the raw transcript."""
    return CallReport(
        source_file=state["source_file"],
        status=status_for_report(state),
        status_reason=state.get("status_reason"),
        stages_completed=tuple(state.get("stages_completed") or ()),
        audit=tuple(state.get("audit") or ()),
        redacted_transcript=state.get("redacted_transcript"),
        summary=state.get("summary"),
        qa_scores=state.get("qa_scores"),
    )


def write_json(report: CallReport, path: Path) -> Path:
    """Write ``report`` to ``path`` (parent dirs created) and return ``path``."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
