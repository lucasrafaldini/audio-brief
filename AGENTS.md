# AGENTS.md — Project guide for AI coding agents

## What this project is

`audio-brief` is a Python CLI that records or transcribes audio with
OpenAI Whisper and produces summaries, keywords, mind maps and transcripts.

## Layout

- `audio_brief/cli.py` — argparse CLI (`record` / `transcribe` / `doctor`). Thin layer; model cached via `_get_model()`, outputs via `writers.write_all()`
- `audio_brief/recorder.py` — mic recording backends (`arecord`, `ffmpeg`, `sox rec`); `backend_status()`, `list_devices()`
- `audio_brief/textproc.py` — offline extractive summarization, keywords, clustering, `stats()`; stopwords EN/ES/FR/DE/PT
- `audio_brief/writers.py` — `write_all()` writes all 10 artifacts (txt/srt/vtt/json/md/mmd/html); summary/keywords computed once
- `tests/` — pytest suite (Whisper stubbed, see `test_cli.py::fake_whisper`)
- `.claude/skills/audio-brief/SKILL.md` — Claude skill for this repo
- `audio-brief` — bash launcher (venv → installed entry point → python3)
- `install.sh` — one-shot setup
- `setup.py` — py2app config for the macOS app bundle
- `.github/workflows/ci.yml` — CI on Linux + macOS, Python 3.10–3.12

## Setup / test

```bash
./install.sh                 # creates .venv, installs -e .
./audio-brief doctor         # environment check
./audio-brief --help
python3 -m pytest tests/ -q  # offline, no Whisper download needed
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
