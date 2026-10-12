"""Report stage: JSON and PDF reports from final pipeline state, always runs."""

from call_center.models import AuditEvent
from call_center.persistence import llm_provider_from_env, persist_call_report
from call_center.reports import artifact_paths, finalized_report, write_json, write_pdf
from call_center.state import PipelineState

NAME = "report"


def run(state: PipelineState) -> dict:
    json_path, pdf_path = artifact_paths(state)
    detail = f"wrote {json_path.resolve()} and {pdf_path.resolve()}"
    report_event = AuditEvent(stage=NAME, outcome="ok", detail=detail)
    report = finalized_report(state, report_event)

    json_written = write_json(report, json_path)
    pdf_written = write_pdf(report, pdf_path)
    persist_call_report(
        report,
        report_json_path=str(json_written),
        report_pdf_path=str(pdf_written),
        llm_provider=llm_provider_from_env(),
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
