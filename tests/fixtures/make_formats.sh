#!/bin/sh
# Regenerate tone.{mp3,flac,ogg,m4a}: a 1 s, 440 Hz, 16 kHz mono tone (needs ffmpeg).
# bitexact flags keep encoder version tags out, so the bytes do not record the ffmpeg build.
set -eu
cd "$(dirname "$0")"
for ext in mp3 flac ogg m4a; do
    ffmpeg -loglevel error -y -f lavfi -i sine=frequency=440:duration=1:sample_rate=16000 \
        -ac 1 -map_metadata -1 -fflags +bitexact -flags:a +bitexact -write_id3v2 0 "tone.$ext"
done
