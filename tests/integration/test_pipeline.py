import json
from pathlib import Path

import pytest

from call_center.cli import main
from call_center.graph import run_pipeline
from call_center.models import AuditEvent, QAScores, Summary, Transcript

SAMPLE = Path(__file__).parent.parent / "fixtures" / "sample.wav"
EXPECTED = [
    "intake",
    "transcription",
    "injection_detection",
    "pii_redaction",
    "summarization",
    "qa_scoring",
    "report",
]


def test_run_pipeline_completes_stages_in_order():
    state = run_pipeline(str(SAMPLE))
    assert state["stages_completed"] == EXPECTED
    assert state["source_file"] == str(SAMPLE)


def test_run_pipeline_final_state_matches_contract():
    state = run_pipeline(str(SAMPLE))
    for key, model in [
        ("transcript", Transcript),
        ("redacted_transcript", Transcript),
        ("summary", Summary),
        ("qa_scores", QAScores),
    ]:
        assert isinstance(state[key], model), key
        model.model_validate(state[key].model_dump(), strict=False)
    assert state["status"] == "completed"
    assert state["status_reason"] is None
    assert len(state["audit"]) == 7
    for event, name in zip(state["audit"], EXPECTED, strict=True):
        assert isinstance(event, AuditEvent)
        AuditEvent.model_validate(event.model_dump())
        assert (event.stage, event.outcome) == (name, "ok")


def test_cli_happy_path_writes_report(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["analyze", str(SAMPLE)]) == 0
    out = Path("reports") / "sample.json"
    assert capsys.readouterr().out.strip() == str(out)
    report = json.loads(out.read_text())
    assert report["source_file"] == str(SAMPLE)
    assert report["status"] == "stub"
    assert report["stages_completed"] == EXPECTED


def test_cli_custom_out_dir_is_created(tmp_path, capsys):
    out_dir = tmp_path / "nested" / "out"
    assert main(["analyze", str(SAMPLE), "--out", str(out_dir)]) == 0
    out = out_dir / "sample.json"
    assert capsys.readouterr().out.strip() == str(out)
    assert json.loads(out.read_text())["stages_completed"] == EXPECTED


def test_cli_missing_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["analyze", "nope.wav"]) == 2
    assert capsys.readouterr().err.strip() == "file not found: nope.wav"
    assert list(tmp_path.iterdir()) == []


def test_cli_path_is_directory(tmp_path, monkeypatch, capsys):
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    assert main(["analyze", "tests/"]) == 2
    assert capsys.readouterr().err.strip() == "not a file: tests"
    assert [p.name for p in tmp_path.iterdir()] == ["tests"]


@pytest.mark.parametrize(
    ("var", "value", "allowed"),
    [
        ("LLM_PROVIDER", "claude", ["openai", "gemini", "groq"]),
        ("WHISPER_MODEL_SIZE", "huge", ["tiny", "base", "small", "medium", "large-v3"]),
    ],
)
def test_cli_invalid_config_exits_2(tmp_path, monkeypatch, capsys, var, value, allowed):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(var, value)
    assert main(["analyze", str(SAMPLE)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("invalid configuration:")
    assert var in captured.err
    for name in allowed:
        assert name in captured.err
    assert value not in captured.err
    assert list(tmp_path.iterdir()) == []


def test_cli_without_key_succeeds_with_tracing_off(tmp_path, monkeypatch):
    import os

    from langsmith import utils as ls_utils

    monkeypatch.setenv("LANGSMITH_TRACING_V2", "true")
    assert main(["analyze", str(SAMPLE), "--out", str(tmp_path)]) == 0
    ls_utils.get_env_var.cache_clear()
    assert ls_utils.tracing_is_enabled() is False
    ls_utils.get_env_var.cache_clear()
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_cli_rejected_file_writes_report_and_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "fake.wav"
    fake.write_text("meeting notes, not audio\n")
    assert main(["analyze", str(fake)]) == 2
    out = Path("reports") / "fake.json"
    captured = capsys.readouterr()
    assert captured.out.strip() == str(out)
    assert captured.err.startswith("rejected: unsupported format")
    assert captured.err.count("\n") == 1
    report = json.loads(out.read_text())
    assert report["source_file"] == str(fake)
    assert report["stages_completed"] == ["intake", "report"]


def test_cli_transcription_failure_exits_2(tmp_path, monkeypatch, capsys):
    from call_center import asr

    class Broken:
        def transcribe(self, path):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(asr, "get_transcriber", lambda model_size: Broken())
    assert main(["analyze", str(SAMPLE), "--out", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out.strip() == str(tmp_path / "sample.json")
    assert captured.err.strip() == "transcription failed: RuntimeError: model exploded"
    assert json.loads((tmp_path / "sample.json").read_text())["stages_completed"] == [
        "intake",
        "transcription",
        "report",
    ]


def test_cli_blocked_run_exits_2(tmp_path, monkeypatch, capsys):
    from call_center.stages import injection_detection

    def blocked(state):
        return {
            "stages_completed": [injection_detection.NAME],
            "status": "blocked",
            "status_reason": "prompt injection detected",
            "audit": [AuditEvent(stage=injection_detection.NAME, outcome="blocked")],
        }

    monkeypatch.setattr(injection_detection, "run", blocked)
    assert main(["analyze", str(SAMPLE), "--out", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out.strip() == str(tmp_path / "sample.json")
    assert captured.err.strip() == "blocked: prompt injection detected"
    assert (tmp_path / "sample.json").exists()
