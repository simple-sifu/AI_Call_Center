"""Pipeline state contract shared by every stage.

The top level is a TypedDict so LangGraph merges each stage's partial update; the values
inside are the frozen Pydantic models from ``call_center.models``. Each value field is
``None`` until the stage that owns it runs.
"""

import operator
from typing import Annotated, TypedDict

from call_center.models import AuditEvent, QAScores, RunStatus, Summary, Transcript


class PipelineState(TypedDict):
    source_file: str
    stages_completed: Annotated[list[str], operator.add]
    transcript: Transcript | None
    redacted_transcript: Transcript | None
    summary: Summary | None
    qa_scores: QAScores | None
    audit: Annotated[list[AuditEvent], operator.add]
    status: RunStatus
    status_reason: str | None
