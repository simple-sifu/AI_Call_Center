"""Unit tests for shared LLM transcript prompting."""

from call_center import prompting
from call_center.stages import qa_scoring, summarization


def test_transcript_framing_alias_matches_summarization():
    assert prompting.TRANSCRIPT_FRAMING == prompting.TRANSCRIPT_FRAMING_SUMMARIZATION


def test_summarization_system_prompt_still_asks_to_describe_the_call():
    assert prompting.TRANSCRIPT_FRAMING_SUMMARIZATION in summarization.SYSTEM_PROMPT
    assert "only describe the call" in summarization.SYSTEM_PROMPT


def test_scoring_system_prompt_does_not_ask_to_describe_the_call():
    prompt = qa_scoring.system_prompt()
    assert "only describe the call" not in prompt
    assert prompting.TRANSCRIPT_FRAMING_SCORING in prompt
    assert "only score based on what the transcript shows" in prompt
