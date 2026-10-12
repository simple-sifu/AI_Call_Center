"""Unit tests for JSON reports and the report stage."""

import json
from pathlib import Path

from helpers import FAKE_QA_SCORES, FAKE_SUMMARY

from call_center.models import AuditEvent, QAScores, Summary, Transcript, TranscriptSegment
from call_center.reports import build_report, write_json
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


def test_report_stage_writes_json(tmp_path):
    out_dir = tmp_path / "out"
    result = report_stage.run(_state(report_output_dir=str(out_dir)))

    path = Path(result["report_json_path"])
    assert path == (out_dir / "sample.json").resolve()
    payload = json.loads(path.read_text())
    assert payload["status"] == "completed"
    assert payload["summary"]["call_purpose"] == FAKE_SUMMARY["call_purpose"]
    assert payload["qa_scores"]["professionalism"]["score"] == 8
    assert payload["stages_completed"][-1] == "report"
    assert payload["audit"][-1]["stage"] == "report"
    assert RAW_TEXT not in path.read_text()
    assert result["status"] == "completed"


def test_write_json_creates_parent_dirs(tmp_path):
    path = tmp_path / "nested" / "dir" / "call.json"
    write_json(build_report(_state(status="blocked", status_reason="x")), path)
    assert path.is_file()
