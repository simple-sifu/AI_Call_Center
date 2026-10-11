"""Regenerate call_stereo.wav and call_mono.wav: a 4-turn two-voice call (macOS ``say``).

The agent (Samantha) is on the left channel and the customer (Daniel) on the right, with
silence on the other channel during each turn. ``call_mono.wav`` is the mix of the two.
Output is 16 kHz, 16-bit PCM. Requires macOS; the committed WAVs make this optional.
"""

import array
import subprocess
import tempfile
import wave
from pathlib import Path

RATE = 16_000
GAP_SECONDS = 0.4
TURNS = [
    ("agent", "Samantha", "Thank you for calling Acme support, this is Sarah. How can I help?"),
    ("customer", "Daniel", "Hi, my internet has been dropping out since yesterday."),
    ("agent", "Samantha", "I'm sorry to hear that. Let me run a quick line test for you."),
    ("customer", "Daniel", "Great, thanks for your help."),
]


def _render(voice: str, text: str, workdir: Path) -> array.array:
    out = workdir / "turn.wav"
    subprocess.run(
        ["say", "-v", voice, "--data-format=LEI16@16000", "-o", str(out), text], check=True
    )
    with wave.open(str(out), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, RATE)
        samples = array.array("h", wav.readframes(wav.getnframes()))
    return samples


def _write(path: Path, channels: int, samples: array.array) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(samples.tobytes())


def main() -> None:
    here = Path(__file__).parent
    left, right = array.array("h"), array.array("h")
    gap = array.array("h", [0]) * int(RATE * GAP_SECONDS)
    with tempfile.TemporaryDirectory() as tmp:
        for role, voice, text in TURNS:
            speech = _render(voice, text, Path(tmp))
            silence = array.array("h", [0]) * len(speech)
            left.extend(speech if role == "agent" else silence)
            right.extend(silence if role == "agent" else speech)
            left.extend(gap)
            right.extend(gap)

    stereo = array.array("h", [0]) * (2 * len(left))
    stereo[0::2], stereo[1::2] = left, right
    # Only one channel speaks at a time, so the sum never clips.
    mono = array.array("h", (a + b for a, b in zip(left, right, strict=True)))
    _write(here / "call_stereo.wav", 2, stereo)
    _write(here / "call_mono.wav", 1, mono)


if __name__ == "__main__":
    main()
