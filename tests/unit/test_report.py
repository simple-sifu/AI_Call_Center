"""Unit tests for JSON reports and the report stage."""

import json
from pathlib import Path

from helpers import FAKE_QA_SCORES, FAKE_SUMMARY
from pypdf import PdfReader

from call_center.models import AuditEvent, QAScores, Summary, Transcript, TranscriptSegment
from call_center.reports import CallReport, build_report, write_json, write_pdf
from call_center.stages import report as report_stage
from call_center.state import PipelineState

RAW_TEXT = "4539148803436467 secret raw line"
REDACTED = Transcript(
    segments=[
        TranscriptSegment(speaker="agent", start=0, end=1, text="Hello"),
        TranscriptSegment(speaker="customer", start=1, end=2, text="My card [CARD]"),
    ],
    audio_sha256="a" * 64,
)
RAW = Transcript(
    segments=[TranscriptSegment(speaker="customer", start=0, end=1, text=RAW_TEXT)],
    audio_sha256="b" * 64,
)


def _state(**overrides) -> PipelineState:
    base: PipelineState = {
        "source_file": "/calls/sample.wav",
        "stages_completed": ["intake", "summarization"],
        "transcript": RAW,
        "redacted_transcript": REDACTED,
        "summary": Summary.model_validate(FAKE_SUMMARY),
        "qa_scores": QAScores.model_validate(FAKE_QA_SCORES),
        "audit": [AuditEvent(stage="intake", outcome="ok")],
        "status": "running",
        "status_reason": None,
        "report_output_dir": None,
        "report_json_path": None,
        "report_pdf_path": None,
    }
    base.update(overrides)
    return base


def test_build_report_omits_the_raw_transcript():
    document = build_report(_state())
    dumped = document.model_dump(mode="json")
    assert "transcript" not in dumped
    assert RAW_TEXT not in json.dumps(dumped)
    assert document.redacted_transcript == REDACTED
    assert document.status == "completed"
    assert document.qa_scores is not None
    assert document.qa_scores.overall == 77.0


def test_build_report_keeps_blocked_and_failed_status():
    blocked = build_report(_state(status="blocked", status_reason="INJ-01"))
    assert blocked.status == "blocked"
    failed = build_report(_state(status="failed", status_reason="rejected: bad file"))
    assert failed.status == "failed"


def _pdf_text(path: Path) -> str:
    return "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)


def test_json_and_pdf_agree_on_key_fields(tmp_path):
    report = build_report(_state())
    event = AuditEvent(stage="report", outcome="ok", detail="wrote paths")
    report = CallReport(
        source_file=report.source_file,
        status="completed",
        status_reason=report.status_reason,
        stages_completed=(*report.stages_completed, "report"),
        audit=(*report.audit, event),
        redacted_transcript=report.redacted_transcript,
        summary=report.summary,
        qa_scores=report.qa_scores,
    )
    json_path = tmp_path / "sample.json"
    pdf_path = tmp_path / "sample.pdf"
    write_json(report, json_path)
    write_pdf(report, pdf_path)

    payload = json.loads(json_path.read_text())
    text = _pdf_text(pdf_path)
    assert payload["summary"]["call_purpose"] in text
    assert str(payload["qa_scores"]["overall"]) in text
    assert "Professionalism" in text or "professionalism" in text.lower()
    assert payload["status"] in text
    assert RAW_TEXT not in text


def test_report_stage_writes_json_and_pdf(tmp_path):
    out_dir = tmp_path / "out"
    result = report_stage.run(_state(report_output_dir=str(out_dir)))

    json_file = Path(result["report_json_path"])
    pdf_file = Path(result["report_pdf_path"])
    assert json_file == (out_dir / "sample.json").resolve()
    assert pdf_file == (out_dir / "sample.pdf").resolve()
    payload = json.loads(json_file.read_text())
    assert payload["status"] == "completed"
    assert payload["summary"]["call_purpose"] == FAKE_SUMMARY["call_purpose"]
    assert payload["qa_scores"]["professionalism"]["score"] == 8
    assert payload["stages_completed"][-1] == "report"
    assert payload["audit"][-1]["stage"] == "report"
    assert "and" in payload["audit"][-1]["detail"]
    assert RAW_TEXT not in json_file.read_text()
    assert FAKE_SUMMARY["call_purpose"] in _pdf_text(pdf_file)
    assert result["status"] == "completed"


def test_blocked_pdf_includes_status(tmp_path):
    report = build_report(_state(status="blocked", status_reason="INJ-01"))
    event = AuditEvent(stage="report", outcome="ok", detail="wrote paths")
    report = CallReport(
        source_file=report.source_file,
        status="blocked",
        status_reason="INJ-01",
        stages_completed=(*report.stages_completed, "report"),
        audit=(*report.audit, event),
        redacted_transcript=None,
        summary=None,
        qa_scores=None,
    )
    pdf_path = write_pdf(report, tmp_path / "blocked.pdf")
    text = _pdf_text(pdf_path)
    assert "blocked" in text
    assert "INJ-01" in text


def test_write_json_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "call.json"
    write_json(build_report(_state(status="blocked", status_reason="x")), path)
    assert path.is_file()
