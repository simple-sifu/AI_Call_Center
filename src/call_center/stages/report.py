"""Report stage: JSON report from final pipeline state, always runs."""

import os
from pathlib import Path

from call_center.models import AuditEvent
from call_center.persistence import llm_provider_from_env, persist_call_report
from call_center.reports import CallReport, build_report, write_json
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
    json_path = _output_dir(state) / f"{stem}.json"
    detail = f"wrote {json_path.resolve()}"
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
    written = write_json(report, json_path)
    persist_call_report(report, report_json_path=str(written), llm_provider=llm_provider_from_env())

    update: dict = {
        "stages_completed": [NAME],
        "report_json_path": str(written),
        "audit": [report_event],
    }
    if state.get("status", "running") == "running":
        update["status"] = "completed"
    return update
