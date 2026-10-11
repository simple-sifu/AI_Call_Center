import json
from pathlib import Path

from call_center.cli import main
from call_center.graph import run_pipeline

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
