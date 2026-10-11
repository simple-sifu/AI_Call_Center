"""Speaker labels from channel energy (spike 2.2, variant A).

For stereo audio each segment goes to whichever channel is louder (RMS) within its
time window: ``agent`` for the agent channel, ``customer`` for the other. Ties,
including silence on both channels, go to the agent. Any other channel count gives
every segment the single label ``speaker_1``.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np

from call_center.config import AgentChannel

AGENT = "agent"
CUSTOMER = "customer"
UNSEPARATED = "speaker_1"


class TimedSegment(Protocol):
    start: float
    end: float


def _rms(channel: np.ndarray, start: int, end: int) -> float:
    window = np.asarray(channel[start:end], dtype=np.float64)
    if window.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(window))))


def label_segments(
    segments: Sequence[TimedSegment],
    channels: Sequence[np.ndarray],
    rate: int,
    agent_channel: AgentChannel,
) -> list[str]:
    """One speaker label per segment, in order."""
    if len(channels) != 2:
        return [UNSEPARATED] * len(segments)
    agent_index = 0 if agent_channel == "left" else 1
    agent, customer = channels[agent_index], channels[1 - agent_index]
    labels = []
    for segment in segments:
        start = max(0, int(float(segment.start) * rate))
        end = max(start, int(float(segment.end) * rate))
        louder = _rms(customer, start, end) > _rms(agent, start, end)
        labels.append(CUSTOMER if louder else AGENT)
    return labels
