# audio-brief

Record or transcribe audio with **Whisper** and generate a summary, a mind map,
keywords and transcripts from the content.

Works on **Linux** and **macOS**. Recording backends (picked automatically):
`arecord` on Linux, `ffmpeg` (avfoundation) on macOS, or `sox rec` if present.
Force one with `AUDIO_BRIEF_RECORDER` (e.g. `AUDIO_BRIEF_RECORDER=ffmpeg`); pick
a specific microphone with `AUDIO_BRIEF_MIC` (macOS defaults to input `0`).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install openai-whisper          # installs CPU PyTorch + Whisper
chmod +x audio-brief
```

## Usage

Record from the microphone for 2 minutes, then process:

```bash
./audio-brief record 120
```

Transcribe an existing file:

```bash
./audio-brief transcribe path/to/lecture.mp3
```

You will be asked for the audio **language** (2-3-letter ISO code, or Enter to
auto-detect) and, the first run, for the **Whisper model**.

For precision use a large model (slower on CPU):

```bash
./audio-brief transcribe file.wav --model medium --language en
```

## Outputs

Files are written to `audio-brief-<timestamp>/` next to the audio (or in the
current directory for recordings):

| File | Content |
|------|---------|
| `transcript.txt` / `.srt` / `.vtt` | Text transcript with timestamps + subtitles |
| `transcript.json` | Raw segment data |
| `summary.md` | Extractive summary of key sentences |
| `keywords.md` | Top topics/keywords with frequencies |
| `mindmap.md` | Mind map (editable with https://markmap.js.org) |
| `mindmap.mmd` | Mind map in Mermaid syntax (mermaid.live) |
| `report.md` | Single file bundling everything |

## Tips

- `--model`: `tiny` (fast/fuzzy) ... `turbo`/`large` (accurate, slow on CPU).
- `--language aa_bb`: skip the language prompt (ISO code, e.g. `en`).
- `--out DIR`: choose the output directory.
- `--keep-raw`: keep the recording inside the output folder (`record` only).

## macOS desktop app

If you want a macOS application bundle:

```bash
# 1. Install py2app into your venv
.venv/bin/pip install py2app

# 2. Run py2app to build the app bundle
python3 setup.py py2app -A
```

The built app will appear at `dist/audio-brief.app`. First launch will download
the Whisper model (tiny ≈ 75 MB). Ensure `ffmpeg` is installed (`brew install ffmpeg`)
for microphone recording.

You can also sign the app for distribution:
`codesign --force --deep --sign - dist/audio-brief.app`.