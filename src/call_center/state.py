"""Minimal pipeline state. Placeholder until story 1.1 defines the full contract."""

import operator
from typing import Annotated, TypedDict


class PipelineState(TypedDict):
    source_file: str
    stages_completed: Annotated[list[str], operator.add]
