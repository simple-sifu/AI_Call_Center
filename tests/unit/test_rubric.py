"""The QA rubric as data, and the prompt text built from it."""

from call_center import rubric
from call_center.models import QA_WEIGHTS, QAScores
from call_center.stages import qa_scoring

CHECKS = [
    "The agent gives their name and the company's name.",
    "The customer is told the call may be recorded.",
    "The customer's identity is verified before account details are discussed.",
    "The agent makes no promises the company cannot keep.",
]


def test_one_entry_per_scored_dimension_in_order():
    names = [d.name for d in rubric.DIMENSIONS]
    assert names == list(QA_WEIGHTS)
    assert set(names) == set(QAScores.model_json_schema()["properties"])


def test_every_dimension_describes_low_middle_and_high():
    for dimension in rubric.DIMENSIONS:
        for text in (dimension.covers, dimension.low, dimension.middle, dimension.high):
            assert text.strip(), dimension.name
        assert len({dimension.low, dimension.middle, dimension.high}) == 3


def test_compliance_checks_are_the_chosen_list():
    assert rubric.COMPLIANCE_CHECKS == CHECKS


def test_render_names_every_dimension_band_and_check():
    text = rubric.render()
    for dimension in rubric.DIMENSIONS:
        assert f"{dimension.name}: {dimension.covers}." in text
        assert f"1-3: {dimension.low}." in text
        assert f"4-7: {dimension.middle}." in text
        assert f"8-10: {dimension.high}." in text
    for check in CHECKS:
        assert f"- {check}" in text


def test_prompt_follows_edits_to_the_compliance_list(monkeypatch):
    added = "The agent confirms the customer's callback number."
    monkeypatch.setattr(rubric, "COMPLIANCE_CHECKS", [*CHECKS, added])
    assert added in qa_scoring.system_prompt()
    monkeypatch.setattr(rubric, "COMPLIANCE_CHECKS", CHECKS[1:])
    prompt = qa_scoring.system_prompt()
    assert CHECKS[0] not in prompt and added not in prompt
    for check in CHECKS[1:]:
        assert check in prompt


def test_prompt_never_asks_the_model_for_an_overall():
    prompt = qa_scoring.system_prompt()
    assert "Do not return an overall score" in prompt
    assert "1 to 10" in prompt
