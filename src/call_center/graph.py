"""LangGraph wiring for the pipeline. The stage order lives only in STAGES."""

from itertools import pairwise

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
from call_center.state import PipelineState, initial_state

STAGES = [
    intake,
    transcription,
    injection_detection,
    pii_redaction,
    summarization,
    qa_scoring,
    report,
]


# Statuses that stop the run: remaining stages are skipped and the report stage records it.
HALTED = ("blocked", "failed")


def _router(next_name: str, report_name: str):
    def route(state: PipelineState) -> str:
        return report_name if state.get("status") in HALTED else next_name

    return route


def build_graph():
    graph = StateGraph(PipelineState)
    for stage in STAGES:
        graph.add_node(stage.NAME, stage.run)
    report_name = STAGES[-1].NAME
    graph.add_edge(START, STAGES[0].NAME)
    for a, b in pairwise(STAGES):
        if b.NAME == report_name:
            graph.add_edge(a.NAME, b.NAME)
        else:
            graph.add_conditional_edges(a.NAME, _router(b.NAME, report_name), [b.NAME, report_name])
    graph.add_edge(report_name, END)
    return graph.compile()


def run_pipeline(path: str) -> dict:
    return build_graph().invoke(initial_state(path))
