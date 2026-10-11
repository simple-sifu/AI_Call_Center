"""LangGraph wiring for the pipeline. The stage order lives only in STAGES."""

from langgraph.graph import END, START, StateGraph

from call_center.stages import (
    injection_detection,
    intake,
    pii_redaction,
    qa_scoring,
    report,
    summarization,
    transcription,
)
from call_center.state import PipelineState

STAGES = [
    intake,
    transcription,
    injection_detection,
    pii_redaction,
    summarization,
    qa_scoring,
    report,
]


def build_graph():
    graph = StateGraph(PipelineState)
    for stage in STAGES:
        graph.add_node(stage.NAME, stage.run)
    graph.add_edge(START, STAGES[0].NAME)
    for a, b in zip(STAGES, STAGES[1:], strict=False):
        graph.add_edge(a.NAME, b.NAME)
    graph.add_edge(STAGES[-1].NAME, END)
    return graph.compile()


def run_pipeline(path: str) -> dict:
    return build_graph().invoke({"source_file": str(path), "stages_completed": []})
