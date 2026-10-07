# AGENTS.md — Project guide for AI coding agents

## What this project is

`audio-brief` is a Python CLI that records or transcribes audio with
OpenAI Whisper and produces summaries, keywords, mind maps and transcripts.

## Layout

- `audio_brief/cli.py` — argparse CLI (`record` / `transcribe` subcommands). Thin layer; keep it.
- `audio_brief/recorder.py` — mic recording backends (`arecord`, `ffmpeg`, `sox rec`)
- `audio_brief/textproc.py` — offline extractive summarization, keywords, clustering
- `audio_brief/writers.py` — output writers (txt/srt/vtt/json/md)
- `audio-brief` — bash launcher (venv → installed entry point → python3)
- `install.sh` — one-shot setup
- `setup.py` — py2app config for the macOS app bundle

## Setup / test

```bash
./install.sh                 # creates .venv, installs -e .
./audio-brief --help
python3 -m py_compile audio_brief/*.py
```

Transcription requires Whisper + model download, so test pure-text paths
(`textproc`, `writers`) without it.

## Conventions

- Python 3.10+, type hints, `from __future__ import annotations`
- No new heavy dependencies; Whisper/torch stay the only big deps
- Keep the CLI non-interactive when stdin/stdout is not a TTY
- Outputs go to `audio-brief-<timestamp>/`; never commit generated runs
  (`.gitignore` covers `audio-brief-*/`)
- Docs are trilingual: `README.md` (en), `README.pt-BR.md`, `README.es.md` —
  keep all three in sync when changing user-facing docs

## Agent behavior

- Prefer reading code before editing; match existing style
- Before finishing, run a compile check and the CLI `--help`
- Don't commit generated example outputs, audio files, or `.venv`
