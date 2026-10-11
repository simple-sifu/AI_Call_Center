"""Guard: no LLM-backed stage may run before injection screening and PII redaction."""

from call_center.graph import STAGES

NAMES = [m.NAME for m in STAGES]


def test_screening_precedes_llm_stages():
    for guard in ("injection_detection", "pii_redaction"):
        for llm_stage in ("summarization", "qa_scoring"):
            assert NAMES.index(guard) < NAMES.index(llm_stage)
