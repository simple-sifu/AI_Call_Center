"""Observability fields persisted on each call row."""

from pathlib import Path

from test_persistence import _completed_report

from call_center.graph import run_pipeline
from call_center.models import AuditEvent
from call_center.observability import list_observability_records, record_from_row
from call_center.persistence import (
    get_engine,
    persist_call_report,
    read_call,
    stage_outcomes_from_report,
)
from call_center.stages import injection_detection

SAMPLE = Path(__file__).parent.parent / "fixtures" / "sample.wav"


def test_stage_outcomes_from_audit_events():
    report = _completed_report()
    outcomes = stage_outcomes_from_report(report)
    assert outcomes["intake"] == "ok"
    assert outcomes["report"] == "ok"


def test_completed_run_persists_observability_fields():
    run_pipeline(str(SAMPLE))
    [record] = list_observability_records()
    assert record.status == "completed"
    assert record.llm_provider == "openai"
    assert record.overall == 77.0
    assert record.analyzed_at.tzinfo is not None
    assert record.stage_outcomes["summarization"] == "ok"
    assert record.stage_outcomes["qa_scoring"] == "ok"
    assert record.llm_prompt_tokens is None
    assert record.llm_completion_tokens is None
    assert record.llm_cost_usd is None
    assert record.pipeline_duration_ms is None

    row = read_call(get_engine(), record.call_id)
    assert row is not None
    assert row.report_pdf_path is not None
    assert row.report_pdf_path.endswith(".pdf")


def test_blocked_run_persists_observability_fields(monkeypatch):
    def blocked(state):
        return {
            "stages_completed": [injection_detection.NAME],
            "status": "blocked",
            "status_reason": "prompt injection detected",
            "audit": [AuditEvent(stage=injection_detection.NAME, outcome="blocked")],
        }

    monkeypatch.setattr(injection_detection, "run", blocked)
    run_pipeline(str(SAMPLE))
    [record] = list_observability_records()
    assert record.status == "blocked"
    assert record.overall is None
    assert record.stage_outcomes["injection_detection"] == "blocked"


def test_failed_intake_persists_observability_fields(monkeypatch, tmp_path):
    from call_center.stages import intake

    def rejected(state):
        return {
            "stages_completed": [intake.NAME],
            "status": "failed",
            "status_reason": "rejected: unsupported format",
            "audit": [AuditEvent(stage=intake.NAME, outcome="failed", detail="rejected")],
        }

    monkeypatch.setattr(intake, "run", rejected)
    run_pipeline(str(tmp_path / "fake.wav"))
    [record] = list_observability_records()
    assert record.status == "failed"
    assert record.overall is None
    assert record.stage_outcomes["intake"] == "failed"


def test_record_from_row_round_trip():
    engine = get_engine()
    report = _completed_report()
    call_id = persist_call_report(
        report,
        report_json_path="/r/sample.json",
        report_pdf_path="/r/sample.pdf",
        engine=engine,
    )
    row = read_call(engine, call_id)
    record = record_from_row(row)
    assert record.call_id == call_id
    assert record.stage_outcomes == stage_outcomes_from_report(report)
