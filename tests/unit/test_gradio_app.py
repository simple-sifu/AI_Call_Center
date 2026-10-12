"""Gradio UI helpers and analyze flow (Epic 6)."""

from datetime import UTC, datetime
from pathlib import Path

import gradio as gr
import pytest
from helpers import FAKE_QA_SCORES, FAKE_SUMMARY

from call_center.config import Settings
from call_center.gradio_app import (
    build_app,
    observability_rows,
    resolve_upload_path,
    run_analyze,
    scores_markdown,
    status_markdown,
    summary_markdown,
)
from call_center.models import QAScores, Summary
from call_center.observability import ObservabilityRecord

SAMPLE = Path(__file__).parent.parent / "fixtures" / "sample.wav"


def test_status_markdown_terminal_states():
    assert "completed" in status_markdown("completed", None)
    assert "INJ-01" in status_markdown("blocked", "INJ-01: injection")
    assert "rejected" in status_markdown("failed", "rejected: bad file")


def test_summary_and_scores_markdown_when_missing():
    assert "No summary" in summary_markdown(None)
    assert "No QA scores" in scores_markdown(None)


def test_summary_and_scores_markdown_when_present():
    summary = Summary.model_validate(FAKE_SUMMARY)
    qa = QAScores.model_validate(FAKE_QA_SCORES)
    text = summary_markdown(summary)
    assert FAKE_SUMMARY["call_purpose"] in text
    assert "negative" in text
    scores = scores_markdown(qa)
    assert "77.0" in scores
    assert "Professionalism" in scores


def test_observability_rows_shape():
    record = ObservabilityRecord(
        call_id=1,
        source_file="/calls/sample.wav",
        status="completed",
        llm_provider="openai",
        overall=77.0,
        analyzed_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        stage_outcomes={"intake": "ok", "report": "ok"},
        llm_prompt_tokens=None,
        llm_completion_tokens=None,
        llm_cost_usd=None,
        pipeline_duration_ms=None,
    )
    [row] = observability_rows([record])
    assert row[0] == 1
    assert row[1] == "sample.wav"
    assert row[2] == "completed"
    assert "intake=ok" in row[6]


def test_run_analyze_completed(monkeypatch, tmp_path):
    summary = Summary.model_validate(FAKE_SUMMARY)
    qa = QAScores.model_validate(FAKE_QA_SCORES)
    json_path = tmp_path / "sample.json"
    pdf_path = tmp_path / "sample.pdf"
    json_path.write_text("{}")
    pdf_path.write_text("pdf")

    def fake_pipeline(path: str, *, report_output_dir=None):
        assert path == str(SAMPLE)
        return {
            "status": "completed",
            "status_reason": None,
            "summary": summary,
            "qa_scores": qa,
            "report_json_path": str(json_path),
            "report_pdf_path": str(pdf_path),
        }

    monkeypatch.setattr("call_center.gradio_app.run_pipeline", fake_pipeline)
    monkeypatch.setattr("call_center.gradio_app.configure_tracing", lambda _s: False)

    view = run_analyze(SAMPLE, settings=Settings(_env_file=None))
    assert "completed" in view.status_md
    assert FAKE_SUMMARY["call_purpose"] in view.summary_md
    assert view.json_path == str(json_path)
    assert view.pdf_path == str(pdf_path)


def test_run_analyze_blocked_shows_reason(monkeypatch, tmp_path):
    def fake_pipeline(path: str, *, report_output_dir=None):
        return {
            "status": "blocked",
            "status_reason": "INJ-01: prompt injection",
            "summary": None,
            "qa_scores": None,
            "report_json_path": str(tmp_path / "x.json"),
            "report_pdf_path": str(tmp_path / "x.pdf"),
        }

    monkeypatch.setattr("call_center.gradio_app.run_pipeline", fake_pipeline)
    monkeypatch.setattr("call_center.gradio_app.configure_tracing", lambda _s: False)
    (tmp_path / "x.json").write_text("{}")
    (tmp_path / "x.pdf").write_text("p")

    view = run_analyze(SAMPLE, settings=Settings(_env_file=None))
    assert "blocked" in view.status_md
    assert "INJ-01" in view.status_md
    assert "No summary" in view.summary_md


def test_build_app_returns_blocks():
    app = build_app(Settings(_env_file=None))
    assert app.__class__.__name__ == "Blocks"


def test_resolve_upload_path(tmp_path):
    wav = tmp_path / "call_mono.wav"
    wav.write_bytes(b"x")
    assert resolve_upload_path(str(wav)) == wav


def test_resolve_upload_path_missing():
    with pytest.raises(gr.Error, match="Upload a WAV"):
        resolve_upload_path(None)
