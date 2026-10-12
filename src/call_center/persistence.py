"""SQLite persistence for analyzed calls and an append-only audit log.

The public API inserts call and audit rows only; there is no update or delete path
for audit entries. Stored JSON fields come from ``CallReport`` (redacted transcript
and analysis only, never the raw transcript).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from call_center.reports import CallReport

__all__ = [
    "AuditRow",
    "CallRow",
    "database_url",
    "get_engine",
    "llm_provider_from_env",
    "persist_call_report",
    "read_call",
    "read_audit_for_call",
    "stage_outcomes_from_report",
]


class Base(DeclarativeBase):
    pass


class CallRow(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String, nullable=False)
    overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_json_path: Mapped[str] = mapped_column(String, nullable=False)
    report_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    stage_outcomes_json: Mapped[str] = mapped_column(Text, nullable=False)
    llm_prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redacted_transcript_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    stages_completed_json: Mapped[str] = mapped_column(Text, nullable=False)


class AuditRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///call_center.db")


def llm_provider_from_env() -> str:
    raw = os.environ.get("LLM_PROVIDER", "openai")
    return raw if raw in ("openai", "gemini", "groq") else "openai"


def get_engine(url: str | None = None):
    return create_engine(url or database_url())


def _ensure_schema(engine) -> None:
    Base.metadata.create_all(engine)


def _json_or_none(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))


def stage_outcomes_from_report(report: CallReport) -> dict[str, str]:
    """Map each audit stage to its outcome (last event wins if a stage repeats)."""
    outcomes: dict[str, str] = {}
    for event in report.audit:
        outcomes[event.stage] = event.outcome
    return outcomes


def persist_call_report(
    report: CallReport,
    *,
    report_json_path: str,
    report_pdf_path: str | None = None,
    llm_provider: str | None = None,
    engine=None,
) -> int:
    """Insert one call row and its audit events; return the new call id."""
    engine = engine or get_engine()
    _ensure_schema(engine)
    provider = llm_provider or llm_provider_from_env()
    overall = report.qa_scores.overall if report.qa_scores is not None else None
    analyzed_at = max((event.at for event in report.audit), default=datetime.now(UTC))

    call = CallRow(
        source_file=report.source_file,
        status=report.status,
        status_reason=report.status_reason,
        llm_provider=provider,
        overall=overall,
        analyzed_at=analyzed_at,
        report_json_path=report_json_path,
        report_pdf_path=report_pdf_path,
        stage_outcomes_json=json.dumps(stage_outcomes_from_report(report)),
        llm_prompt_tokens=None,
        llm_completion_tokens=None,
        llm_cost_usd=None,
        pipeline_duration_ms=None,
        redacted_transcript_json=_json_or_none(
            report.redacted_transcript.model_dump(mode="json")
            if report.redacted_transcript
            else None
        ),
        summary_json=_json_or_none(
            report.summary.model_dump(mode="json") if report.summary else None
        ),
        qa_scores_json=_json_or_none(
            report.qa_scores.model_dump(mode="json") if report.qa_scores else None
        ),
        stages_completed_json=json.dumps(list(report.stages_completed)),
    )

    with Session(engine) as session:
        session.add(call)
        session.flush()
        for event in report.audit:
            session.add(
                AuditRow(
                    call_id=call.id,
                    stage=event.stage,
                    at=event.at,
                    outcome=event.outcome,
                    detail=event.detail,
                )
            )
        session.commit()
        return call.id


def read_call(engine, call_id: int) -> CallRow | None:
    """Read one call row (for tests)."""
    with Session(engine) as session:
        return session.get(CallRow, call_id)


def read_audit_for_call(engine, call_id: int) -> list[AuditRow]:
    """Audit rows for a call, in insertion order (for tests)."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(AuditRow).where(AuditRow.call_id == call_id).order_by(AuditRow.id)
            )
        )
