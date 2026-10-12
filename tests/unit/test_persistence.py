"""SQLite persistence and append-only audit."""

import inspect
from pathlib import Path

from helpers import SAMPLE_RAW_CARD, sample_persist_report
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from call_center import persistence
from call_center.graph import run_pipeline
from call_center.models import AuditEvent
from call_center.persistence import (
    AuditRow,
    CallRow,
    get_engine,
    persist_call_report,
    read_audit_for_call,
)
from call_center.stages import injection_detection
from call_center.stages import report as report_stage

SAMPLE = Path(__file__).parent.parent / "fixtures" / "sample.wav"


def test_public_api_has_no_audit_update_or_delete():
    for name, obj in inspect.getmembers(persistence):
        if name.startswith("_") or not inspect.isfunction(obj):
            continue
        lowered = name.lower()
        assert "update" not in lowered
        assert "delete" not in lowered
        assert "remove" not in lowered


def test_persist_inserts_call_and_audit_rows():
    engine = get_engine()
    report = sample_persist_report(str(SAMPLE))
    call_id = persist_call_report(report, report_json_path="/reports/sample.json", engine=engine)

    call = persistence.read_call(engine, call_id)
    assert call is not None
    assert call.status == "completed"
    assert call.llm_provider == "openai"
    assert call.overall == 77.0
    assert call.summary_json is not None
    assert SAMPLE_RAW_CARD not in (call.redacted_transcript_json or "")
    assert SAMPLE_RAW_CARD not in (call.summary_json or "")

    audits = read_audit_for_call(engine, call_id)
    assert len(audits) == len(report.audit)
    assert [row.stage for row in audits] == [event.stage for event in report.audit]


def test_pipeline_persists_one_call_and_seven_audit_rows():
    engine = get_engine()
    run_pipeline(str(SAMPLE))

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CallRow)) == 1
        assert session.scalar(select(func.count()).select_from(AuditRow)) == 7


def test_report_stage_persists_blocked_runs(monkeypatch, tmp_path):
    report_stage.run(
        {
            "source_file": "/x/mono.wav",
            "stages_completed": ["intake", "transcription", "injection_detection"],
            "transcript": None,
            "redacted_transcript": None,
            "summary": None,
            "qa_scores": None,
            "audit": [AuditEvent(stage="injection_detection", outcome="blocked", detail="x")],
            "status": "blocked",
            "status_reason": "prompt injection detected",
            "report_output_dir": str(tmp_path),
            "report_json_path": None,
            "report_pdf_path": None,
        }
    )

    engine = get_engine()
    with Session(engine) as session:
        call = session.scalar(select(CallRow))
        assert call.status == "blocked"
        assert call.overall is None
        assert session.scalar(select(func.count()).select_from(AuditRow)) == 2


def test_blocked_pipeline_persists(monkeypatch):
    def blocked(state):
        return {
            "stages_completed": [injection_detection.NAME],
            "status": "blocked",
            "status_reason": "prompt injection detected",
            "audit": [AuditEvent(stage=injection_detection.NAME, outcome="blocked")],
        }

    monkeypatch.setattr(injection_detection, "run", blocked)
    run_pipeline(str(SAMPLE))
    engine = get_engine()
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CallRow)) == 1
        assert session.scalar(select(func.count()).select_from(AuditRow)) == 4
