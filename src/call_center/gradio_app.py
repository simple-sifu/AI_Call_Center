"""Gradio 5.x UI: Analyze Call and Observability tabs (Epic 6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from pathlib import Path

import gradio as gr
from pydantic import ValidationError

from call_center.config import Settings, format_config_error, load_settings
from call_center.graph import run_pipeline
from call_center.models import QAScores, Summary
from call_center.observability import ObservabilityRecord, list_observability_records
from call_center.tracing import configure_tracing, flush_traces

_SCORE_DIMENSIONS = (
    ("professionalism", "Professionalism"),
    ("empathy", "Empathy"),
    ("resolution", "Resolution"),
    ("compliance", "Compliance"),
    ("clarity", "Clarity"),
)

_OBSERVABILITY_HEADERS = [
    "ID",
    "Source file",
    "Status",
    "LLM provider",
    "Overall",
    "Analyzed at (UTC)",
    "Stage outcomes",
    "Prompt tokens",
    "Completion tokens",
    "Cost (USD)",
    "Pipeline duration (ms)",
]


@dataclass(frozen=True)
class AnalyzeView:
    """Markdown and download paths for the Analyze Call tab."""

    status_md: str
    summary_md: str
    scores_md: str
    json_path: str | None
    pdf_path: str | None

    def as_tuple(self) -> tuple[str, str, str, str | None, str | None]:
        return self.status_md, self.summary_md, self.scores_md, self.json_path, self.pdf_path


def status_markdown(status: str, reason: str | None) -> str:
    if status == "completed":
        return "**Status:** completed"
    if status == "blocked":
        detail = reason or "no reason given"
        return f"**Status:** blocked — {detail}"
    if status == "failed":
        detail = reason or "failed"
        return f"**Status:** failed — {detail}"
    return f"**Status:** {status}"


def summary_markdown(summary: Summary | None) -> str:
    if summary is None:
        return "_No summary — analysis did not complete._"
    items = "\n".join(f"- {item}" for item in summary.action_items) or "_None_"
    entities = (
        "\n".join(f"- {entity.text} ({entity.type})" for entity in summary.entities) or "_None_"
    )
    traj = summary.sentiment_trajectory
    return (
        f"**Purpose:** {summary.call_purpose}\n\n"
        f"**Action items:**\n{items}\n\n"
        f"**Sentiment:** opening {traj.opening}, middle {traj.middle}, closing {traj.closing}\n\n"
        f"**Entities:**\n{entities}"
    )


def scores_markdown(qa: QAScores | None) -> str:
    if qa is None:
        return "_No QA scores — analysis did not complete._"
    lines = [f"**Overall:** {qa.overall}"]
    for key, label in _SCORE_DIMENSIONS:
        dim = getattr(qa, key)
        lines.append(f"- **{label}** ({dim.score}/10): {dim.rationale}")
    return "\n".join(lines)


def observability_rows(
    records: tuple[ObservabilityRecord, ...] | list[ObservabilityRecord],
) -> list[list[object]]:
    rows: list[list[object]] = []
    for record in records:
        stages = ", ".join(
            f"{stage}={outcome}" for stage, outcome in sorted(record.stage_outcomes.items())
        )
        rows.append(
            [
                record.call_id,
                Path(record.source_file).name,
                record.status,
                record.llm_provider,
                record.overall,
                record.analyzed_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
                stages,
                record.llm_prompt_tokens,
                record.llm_completion_tokens,
                record.llm_cost_usd,
                record.pipeline_duration_ms,
            ]
        )
    return rows


def run_analyze(source: Path, *, settings: Settings) -> AnalyzeView:
    """Run the pipeline on ``source`` and format UI fields (no Gradio dependency)."""
    tracing = configure_tracing(settings)
    try:
        state = run_pipeline(str(source), report_output_dir=settings.report_output_dir)
    finally:
        if tracing:
            flush_traces()

    status = state["status"]
    reason = state.get("status_reason")
    summary = state.get("summary")
    qa = state.get("qa_scores")
    json_path = state.get("report_json_path")
    pdf_path = state.get("report_pdf_path")

    return AnalyzeView(
        status_md=status_markdown(status, reason),
        summary_md=summary_markdown(summary),
        scores_md=scores_markdown(qa),
        json_path=json_path,
        pdf_path=pdf_path,
    )


def resolve_upload_path(upload: str | None) -> Path:
    """Turn a Gradio file/audio filepath into a readable ``Path``."""
    if not upload:
        raise gr.Error("Upload a WAV file first.")
    path = Path(upload)
    if not path.is_file():
        raise gr.Error(f"Upload is not a file: {path}")
    return path


def _analyze_handler(
    upload_path: str | None,
) -> tuple[str, str, str, str | None, str | None]:
    path = resolve_upload_path(upload_path)
    try:
        settings = load_settings()
    except ValidationError as error:
        raise gr.Error(format_config_error(error)) from None
    try:
        return run_analyze(path, settings=settings).as_tuple()
    except Exception as error:
        raise gr.Error(str(error)) from None


def _refresh_observability() -> list[list[object]]:
    return observability_rows(list_observability_records())


def build_app(settings: Settings | None = None) -> gr.Blocks:
    """Two-tab Gradio app; optional ``settings`` validates config at build time."""
    _ = settings or load_settings()
    with gr.Blocks(title="Call Center Intelligence") as demo:
        gr.Markdown("# Call Center Intelligence")
        with gr.Tabs():
            with gr.Tab("Analyze Call"):
                gr.Markdown(
                    "Upload a **WAV** file (use **call_mono.wav** or **call_stereo.wav** in "
                    "`tests/fixtures/` — not the 1 s `sample.wav`). Analysis can take several "
                    "minutes on CPU. JSON/PDF reports and SQLite rows are written when the run "
                    "finishes."
                )
                upload = gr.File(
                    label="Call recording (WAV)",
                    file_types=[".wav"],
                    type="filepath",
                )
                analyze_btn = gr.Button("Analyze", variant="primary")
                status_out = gr.Markdown(label="Status")
                summary_out = gr.Markdown(label="Summary")
                scores_out = gr.Markdown(label="QA scores")
                with gr.Row():
                    json_out = gr.File(label="JSON report")
                    pdf_out = gr.File(label="PDF report")
                analyze_btn.click(
                    fn=_analyze_handler,
                    inputs=upload,
                    outputs=[status_out, summary_out, scores_out, json_out, pdf_out],
                )
            with gr.Tab("Observability"):
                gr.Markdown("Persisted calls from SQLite (newest first).")
                refresh_btn = gr.Button("Refresh")
                table = gr.Dataframe(
                    headers=_OBSERVABILITY_HEADERS,
                    datatype=[
                        "number",
                        "str",
                        "str",
                        "str",
                        "number",
                        "str",
                        "str",
                        "number",
                        "number",
                        "number",
                        "number",
                    ],
                    interactive=False,
                    wrap=True,
                )
                refresh_btn.click(fn=_refresh_observability, outputs=table)
                demo.load(fn=_refresh_observability, outputs=table)
    return demo


def launch(
    *,
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
    settings: Settings | None = None,
) -> None:
    settings = settings or load_settings()
    build_app(settings).launch(server_name=server_name, server_port=server_port, share=share)
