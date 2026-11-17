#!/usr/bin/env bash
# Turns a recorded take into the walkthrough's video and poster (Phase 8, Task 45):
#   encode.sh RAW_WEBM START_SECONDS POSTER_PNG OUT_DIR
# writes OUT_DIR/walkthrough.mp4 (H.264, no sound, 1440 by 900, the moov atom first so a browser
# can start playing before it has the whole file) and OUT_DIR/walkthrough-poster.jpg. It fails if
# the video is larger than MAX_VIDEO_BYTES (8 MB by default): the image serves it from its origin.
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: encode.sh RAW_WEBM START_SECONDS POSTER_PNG OUT_DIR" >&2
  exit 2
fi
raw=$1
start=$2
poster=$3
out=$4
max_bytes=${MAX_VIDEO_BYTES:-8388608}

if ! [[ $start =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
  echo "START_SECONDS must be a number of seconds, not '$start'" >&2
  exit 2
fi
command -v ffmpeg >/dev/null || { echo "ffmpeg is not installed (brew install ffmpeg)" >&2; exit 1; }

mkdir -p "$out"
ffmpeg -loglevel error -y -ss "$start" -i "$raw" -an \
  -vf "scale=1440:900:flags=lanczos,fps=25" \
  -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart \
  "$out/walkthrough.mp4"
ffmpeg -loglevel error -y -i "$poster" -vf "scale=1440:900" -q:v 3 "$out/walkthrough-poster.jpg"

size=$(wc -c < "$out/walkthrough.mp4" | tr -d ' ')
if (( size > max_bytes )); then
  echo "walkthrough.mp4 is $size bytes, over the limit of $max_bytes" >&2
  exit 1
fi
echo "walkthrough.mp4: $size bytes"
