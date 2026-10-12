"""The QA scoring rubric, as data: the QA prompt is built from this module.

``DIMENSIONS`` holds, for each scored dimension, what it covers and what a low, middle
and high score means. ``COMPLIANCE_CHECKS`` is the editable compliance checklist; adding,
removing or rewording an item changes the prompt the model sees. The dimensions and their
weights are fixed by ``models.QAScores`` and ``models.QA_WEIGHTS``; this module only
describes them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    name: str
    covers: str
    low: str  # 1-3
    middle: str  # 4-7
    high: str  # 8-10


# The compliance checklist (user's decision, 2026-10-12). Edit this list to change it.
COMPLIANCE_CHECKS: list[str] = [
    "The agent gives their name and the company's name.",
    "The customer is told the call may be recorded.",
    "The customer's identity is verified before account details are discussed.",
    "The agent makes no promises the company cannot keep.",
]

DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        name="professionalism",
        covers="courtesy, tone and conduct of the agent throughout the call",
        low="rude, dismissive, sarcastic or inappropriate language",
        middle="polite but flat, scripted, or with lapses such as interrupting",
        high="consistently courteous, respectful and composed, even under pressure",
    ),
    Dimension(
        name="empathy",
        covers="how well the agent recognises and responds to the customer's feelings",
        low="ignores or dismisses the customer's frustration or concern",
        middle="acknowledges feelings in passing without adapting to them",
        high="names and validates the customer's feelings and adapts the approach to them",
    ),
    Dimension(
        name="resolution",
        covers="whether the customer's issue was solved or given a clear path to a solution",
        low="the issue is left unresolved with no next step",
        middle="partly resolved, or a next step given that is vague or incomplete",
        high="fully resolved, or a concrete next step agreed and confirmed with the customer",
    ),
    Dimension(
        name="compliance",
        covers="how many of the compliance checks listed below the agent met",
        low="most checks are missed, or a promise the company cannot keep is made",
        middle="some checks are met and others missed",
        high="every check is met",
    ),
    Dimension(
        name="clarity",
        covers="how clearly the agent explains, and whether the customer understood",
        low="confusing, contradictory or full of jargon; the customer is left unsure",
        middle="mostly clear, with some confusion or repetition needed",
        high="clear, concise explanations, with understanding checked",
    ),
)


def render() -> str:
    """The rubric as prompt text: each dimension's bands, then the compliance checklist."""
    parts = []
    for dimension in DIMENSIONS:
        parts.append(
            f"{dimension.name}: {dimension.covers}.\n"
            f"  1-3: {dimension.low}.\n"
            f"  4-7: {dimension.middle}.\n"
            f"  8-10: {dimension.high}."
        )
    checks = "\n".join(f"- {check}" for check in COMPLIANCE_CHECKS)
    parts.append(f"Compliance checks:\n{checks}")
    return "\n\n".join(parts)
