"""JSON call reports built from pipeline state (Epic 5).

Reports include the redacted transcript and analysis results only, never the raw
``transcript``.
"""

import json
from html import escape
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

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


def _p(text: str) -> str:
    return escape(text, quote=False)


def write_pdf(report: CallReport, path: Path) -> Path:
    """Write a human-readable PDF with the same facts as the JSON report."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story: list = [Paragraph("Call analysis report", styles["Title"]), Spacer(1, 12)]

    story.append(Paragraph(f"<b>Source:</b> {_p(report.source_file)}", styles["Normal"]))
    story.append(Paragraph(f"<b>Status:</b> {_p(report.status)}", styles["Normal"]))
    if report.status_reason:
        story.append(
            Paragraph(f"<b>Reason:</b> {_p(report.status_reason)}", styles["Normal"])
        )
    story.append(Spacer(1, 12))

    if report.summary is not None:
        story.append(Paragraph("Summary", styles["Heading2"]))
        story.append(
            Paragraph(
                f"<b>Purpose:</b> {_p(report.summary.call_purpose)}", styles["Normal"]
            )
        )
        if report.summary.action_items:
            items = "; ".join(report.summary.action_items)
            story.append(Paragraph(f"<b>Action items:</b> {_p(items)}", styles["Normal"]))
        traj = report.summary.sentiment_trajectory
        story.append(
            Paragraph(
                f"<b>Sentiment:</b> opening {_p(traj.opening)}, middle {_p(traj.middle)}, "
                f"closing {_p(traj.closing)}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 12))

    if report.qa_scores is not None:
        story.append(Paragraph("QA scores", styles["Heading2"]))
        story.append(
            Paragraph(f"<b>Overall:</b> {report.qa_scores.overall}", styles["Normal"])
        )
        for name in (
            "professionalism",
            "empathy",
            "resolution",
            "compliance",
            "clarity",
        ):
            dimension = getattr(report.qa_scores, name)
            story.append(
                Paragraph(
                    f"<b>{_p(name.title())}:</b> {dimension.score} — "
                    f"{_p(dimension.rationale)}",
                    styles["Normal"],
                )
            )
        story.append(Spacer(1, 12))

    story.append(Paragraph("Audit trail", styles["Heading2"]))
    for event in report.audit:
        line = f"{_p(event.stage)} ({_p(event.outcome)}): {_p(event.detail)}"
        story.append(Paragraph(line, styles["Normal"]))

    SimpleDocTemplate(str(path), pagesize=letter).build(story)
    return path
