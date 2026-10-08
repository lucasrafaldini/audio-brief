---
name: audio-brief
description: Transcribe audio with Whisper and generate summaries, mindmaps and reports. Use when working on the audio-brief repo or when the user wants to turn audio into briefs.
---

# audio-brief skill

## What it does

Records or transcribes audio with OpenAI Whisper and produces a summary,
mind map, keywords, transcripts (txt/srt/vtt/json) and reports (md + html).

## Commands

```bash
./audio-brief doctor                                  # environment check first
./audio-brief transcribe <file> --model base --language en
./audio-brief transcribe a.mp3 b.mp3 --jobs 2        # parallel
./audio-brief record 120 --model base --language pt   # mic recording
```

## Code map

- `audio_brief/cli.py` — argparse CLI; model cached via `_get_model()`; outputs via `writers.write_all()`
- `audio_brief/recorder.py` — backends `arecord`/`ffmpeg`/`sox rec`; `backend_status()`, `list_devices()`
- `audio_brief/textproc.py` — offline NLP: `sentences()`, `summarize()`, `extract_keywords()`, `build_mindmap()`, `stats()`
- `audio_brief/writers.py` — `write_all()` writes all 10 artifacts; summary/keywords computed once

## Rules

- Python 3.10+, type hints, `from __future__ import annotations`
- No new heavy dependencies (torch/whisper stay the only big ones)
- Keep CLI non-interactive when not a TTY
- Never commit `audio-brief-*/`, `*.wav`, `.venv`
- Docs are trilingual (`README.md`, `README.pt-BR.md`, `README.es.md`) — sync all three
- Verify: `python3 -m py_compile audio_brief/*.py` + `python3 -m pytest tests/ -q`
- Transcription tests must stub `whisper` (see `tests/test_cli.py::fake_whisper`)
