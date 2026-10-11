import numpy as np
import pytest

from call_center.asr import RawSegment
from call_center.speakers import label_segments

RATE = 1_000
SEGMENTS = [RawSegment(0.0, 1.0, "one"), RawSegment(1.0, 2.0, "two")]


def _tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return (0.5 * np.sin(2 * np.pi * 50 * t)).astype(np.float32)


def _call(crosstalk: float = 0.0) -> list[np.ndarray]:
    """Left speaks in the first second, right in the second."""
    speech, silence = _tone(1.0), np.zeros(RATE, dtype=np.float32)
    left = np.concatenate([speech, silence])
    right = np.concatenate([silence, speech])
    return [left + crosstalk * right, right + crosstalk * left]


def test_stereo_clean_labels_louder_channel():
    assert label_segments(SEGMENTS, _call(), RATE, "left") == ["agent", "customer"]


def test_stereo_with_30_percent_crosstalk_matches_clean():
    assert label_segments(SEGMENTS, _call(0.3), RATE, "left") == ["agent", "customer"]


def test_agent_on_right_swaps_labels():
    assert label_segments(SEGMENTS, _call(), RATE, "right") == ["customer", "agent"]


@pytest.mark.parametrize("agent_channel", ["left", "right"])
def test_silence_on_both_channels_goes_to_agent(agent_channel):
    silent = [np.zeros(2 * RATE, dtype=np.float32)] * 2
    assert label_segments(SEGMENTS, silent, RATE, agent_channel) == ["agent", "agent"]


def test_equal_energy_goes_to_agent():
    tone = _tone(2.0)
    assert label_segments(SEGMENTS, [tone, tone.copy()], RATE, "right") == ["agent", "agent"]


def test_window_past_end_of_audio_is_a_tie():
    late = [RawSegment(5.0, 6.0, "late"), RawSegment(1.5, 1.5, "empty")]
    assert label_segments(late, _call(), RATE, "left") == ["agent", "agent"]


@pytest.mark.parametrize("count", [0, 1, 3, 6])
def test_other_channel_counts_give_one_label(count):
    channels = [_tone(2.0) for _ in range(count)]
    assert label_segments(SEGMENTS, channels, RATE, "left") == ["speaker_1", "speaker_1"]


def test_no_segments_gives_no_labels():
    assert label_segments([], _call(), RATE, "left") == []
