#!/usr/bin/env bash
# One-shot setup: creates a virtualenv, installs audio-brief into it,
# and makes the `audio-brief` command available at ./audio-brief
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi

[ -d .venv ] || "$PYTHON" -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e .

echo
echo "Done! Try:"
echo "  ./audio-brief --help"
echo "  ./audio-brief transcribe your-audio.mp3"
echo
echo "Tip: add this to your PATH for global access:"
echo "  export PATH=\"$DIR/.venv/bin:\$PATH\""
