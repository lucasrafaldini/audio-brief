# 🎧 audio-brief

> 🌐 **English** · [Português (Brasil)](README.pt-BR.md) · [Español](README.es.md)

[![Hacktoberfest](https://img.shields.io/badge/Hacktoberfest-2026-f74700?style=flat-square)](https://hacktoberfest.com)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

Record or transcribe audio with **OpenAI Whisper** and automatically get a
**summary**, a **mind map**, **keywords**, and ready-to-use transcripts
(`.txt`, `.srt`, `.vtt`, `.json`) — all in one command. No API keys, runs
offline (after the first model download).

Works on **Linux** and **macOS**.

## ✨ Features

- 🎙️ Record from your microphone or transcribe existing audio files
- 🌍 Auto language detection (or force it with `--language`)
- 🧠 Extractive summary, keyword extraction, and mind maps (Markmap + Mermaid)
- 📄 Subtitles in SRT/VTT + bundled `report.md` and `report.html`
- 🩺 `doctor` command checks your environment (Whisper, ffmpeg, mic)
- ⚡ Queue multiple files, optionally in parallel with `--jobs N`
- 🖥️ Friendly CLI: sensible defaults, zero prompts when piped/CI

## 🚀 Quick start

Requires **Python 3.10+** and (for macOS recording) `ffmpeg`
(`brew install ffmpeg` on macOS, `apt install ffmpeg` on Debian/Ubuntu).

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief
./install.sh          # creates .venv and installs everything
```

Then:

```bash
./audio-brief transcribe meeting.mp3        # pick model/language interactively
./audio-brief transcribe meeting.mp3 --model base --language en
./audio-brief record 120                     # record 2 minutes, then transcribe
```

After `install.sh`, you can also add the venv to your PATH and use the command
directly:

```bash
export PATH="$PWD/.venv/bin:$PATH"
audio-brief --help
```

### Alternative installs

```bash
pip install .          # into your current environment
pipx install .         # isolated CLI install
```

## 📖 Usage

```
audio-brief record [seconds] [--model M] [--language L] [--out DIR] [--keep-raw]
audio-brief transcribe <file> [file2 ...] [--jobs N] [--model M] [--language L] [--out DIR]
audio-brief doctor
audio-brief --version
```

| Option | Meaning |
|--------|---------|
| `--model` | `tiny` (fast/fuzzy) → `base` → `small` → `medium` → `large`/`turbo` (accurate, slower) |
| `--language` | 2–3 letter ISO code (e.g. `en`, `pt`, `es`). Skips the prompt; auto-detect if unset |
| `--out DIR` | Choose the output directory |
| `--jobs N` | Transcribe N files in parallel |
| `--summary-n N` | Max sentences in the summary (default: 8) |
| `--keywords-n N` | Max keywords extracted (default: 15) |
| `--keep-raw` | Keep the recorded `.wav` inside the output folder (`record` only) |

Run `audio-brief doctor` first if something doesn't work — it checks
Python, Whisper, recording backends and (on macOS) lists audio devices.

Examples:

```bash
# one file, English, medium model
audio-brief transcribe lecture.wav --model medium --language en

# three files, two at a time
audio-brief transcribe a.mp3 b.mp3 c.mp3 --jobs 2
```

When run interactively you'll be asked for language and model once; when
piped (CI, scripts) it silently uses auto-detect + `base`.

## 📂 Output

Files land in `audio-brief-<timestamp>/` next to the audio (or in the current
directory for recordings):

| File | Content |
|------|---------|
| `transcript.txt` | Timestamped plain-text transcript |
| `transcript.srt` / `.vtt` | Subtitles |
| `transcript.json` | Raw segment data |
| `summary.md` | Key sentences, ranked |
| `keywords.md` | Top topics/keywords with frequencies |
| `mindmap.md` | Mind map (paste into [markmap.js.org](https://markmap.js.org)) |
| `mindmap.mmd` | Mind map in Mermaid ([mermaid.live](https://mermaid.live)) |
| `report.md` | Everything bundled in one Markdown file |
| `report.html` | Same report as a self-contained web page (no viewer needed) |

## ⚙️ Recording backends

Picked automatically: `arecord` (Linux/ALSA) → `ffmpeg` (macOS via
avfoundation, Linux via ALSA) → `sox rec`. Force one and choose a mic:

```bash
AUDIO_BRIEF_RECORDER=ffmpeg AUDIO_BRIEF_MIC=1 audio-brief record 60
# list macOS audio inputs:
ffmpeg -f avfoundation -list_devices true -i ''
```

## 💡 Model sizing

| Model | Size | Speed (CPU) | Quality |
|-------|------|-------------|---------|
| `tiny` | ~75 MB | fastest | fuzzy |
| `base` | ~150 MB | fast | ok for a brief |
| `small` | ~500 MB | medium | good |
| `medium` | ~1.5 GB | slow | great |
| `large`/`turbo` | ~3 GB | slowest | best |

## 🍎 macOS app bundle (optional)

```bash
.venv/bin/pip install py2app
.venv/bin/python setup.py py2app -A
# -> dist/audio-brief.app
```

## 🤝 Contributing

PRs welcome — especially for Hacktoberfest! Ideas:

- Speaker diarization
- LLM-based summaries (optional flag)
- More output formats (HTML, Obsidian, Anki)
- Better Windows support / GUI wrapper

```bash
git clone https://github.com/lucasrafaldini/audio-brief.git
cd audio-brief && ./install.sh
```

Open an issue before large changes so we can align on scope.

See also: [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md) · [LICENSE](LICENSE)

## 📜 License

MIT
