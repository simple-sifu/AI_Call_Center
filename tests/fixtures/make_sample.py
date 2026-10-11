"""Regenerate sample.wav: a 1 s, 440 Hz, 16 kHz mono, 16-bit tone (stdlib only)."""

import math
import struct
import wave
from pathlib import Path

RATE = 16_000
FREQ = 440
SECONDS = 1


def main() -> None:
    path = Path(__file__).with_name("sample.wav")
    frames = b"".join(
        struct.pack("<h", int(0.5 * 32767 * math.sin(2 * math.pi * FREQ * i / RATE)))
        for i in range(RATE * SECONDS)
    )
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(frames)


if __name__ == "__main__":
    main()
