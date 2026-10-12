"""Report stage: JSON and PDF reports from final pipeline state, always runs."""

import os
from pathlib import Path

from call_center.models import AuditEvent
from call_center.persistence import llm_provider_from_env, persist_call_report
from call_center.reports import CallReport, build_report, write_json, write_pdf
from call_center.state import PipelineState

NAME = "report"


def _output_dir(state: PipelineState) -> Path:
    if override := state.get("report_output_dir"):
        return Path(override)
    if raw := os.environ.get("REPORT_OUTPUT_DIR"):
        return Path(raw)
    return Path("reports")


def run(state: PipelineState) -> dict:
    stem = Path(state["source_file"]).stem
    out_dir = _output_dir(state)
    json_path = out_dir / f"{stem}.json"
    pdf_path = out_dir / f"{stem}.pdf"
    detail = f"wrote {json_path.resolve()} and {pdf_path.resolve()}"
    report_event = AuditEvent(stage=NAME, outcome="ok", detail=detail)

    base = build_report(state)
    report = CallReport(
        source_file=base.source_file,
        status=base.status,
        status_reason=base.status_reason,
        stages_completed=(*base.stages_completed, NAME),
        audit=(*base.audit, report_event),
        redacted_transcript=base.redacted_transcript,
        summary=base.summary,
        qa_scores=base.qa_scores,
    )
    json_written = write_json(report, json_path)
    pdf_written = write_pdf(report, pdf_path)
    persist_call_report(
        report, report_json_path=str(json_written), llm_provider=llm_provider_from_env()
    )

    update: dict = {
        "stages_completed": [NAME],
        "report_json_path": str(json_written),
        "report_pdf_path": str(pdf_written),
        "audit": [report_event],
    }
    if state.get("status", "running") == "running":
        update["status"] = "completed"
    return update
