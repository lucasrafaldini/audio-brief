"""Command-line interface for audio-brief."""

from __future__ import annotations

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

from . import __version__
from . import recorder, writers

MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
LANG_RE = re.compile(r"^[a-zA-Z]{2,3}$")


def _ask_language() -> str | None:
    print(
        "\nAudio language? Enter the 2-3 letter ISO code (e.g. en, es, fr, de, it, pt, ja).\n"
        "Press Enter to let Whisper auto-detect."
    )
    while True:
        ans = input("language [auto]: ").strip().lower()
        if not ans:
            return None
        if LANG_RE.match(ans):
            return ans
        print(f"  '{ans}' does not look like a language code. Try e.g. 'en' or 'es'.")


def _ask_model(default: str) -> str:
    print(
        f"\nWhisper model? [{'/'.join(MODELS)}]\n"
        "Bigger = more precise but much slower (CPU). 'base' is a good default."
    )
    while True:
        ans = input(f"model [{default}]: ").strip().lower() or default
        if ans in MODELS:
            return ans
        print(f"  '{ans}' is not valid. Choose one of: {', '.join(MODELS)}")


def _load_audio_path(arg: str) -> Path:
    p = Path(arg).expanduser()
    if not p.exists() or not p.is_file():
        sys.exit(f"Cannot find audio file: {arg}")
    return p


def _timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _process(audio: Path, model_name: str, language: str | None, out_dir: Path) -> None:
    import whisper
    from . import textproc

    print(f"\nLoading Whisper model '{model_name}' ...")
    model = whisper.load_model(model_name)
    lang_msg = language or "auto-detect"
    print(f"Transcribing {audio.name} (language: {lang_msg}) ...\n")

    result = model.transcribe(
        str(audio),
        language=language,
        fp16=False,
        verbose=False,
    )
    text = result.get("text", "").strip()
    if not text:
        print("WARNING: Whisper returned no text. Check that the audio has clear speech.")
    else:
        print(text)

    segments = result.get("segments") or []
    meta = {
        "source": str(audio),
        "model": model_name,
        "language": result.get("language", language),
        "duration": result.get("duration", 0.0),
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    writers.write_transcript_txt(segments, out_dir / "transcript.txt")
    writers.write_transcript_srt(segments, out_dir / "transcript.srt")
    writers.write_transcript_vtt(segments, out_dir / "transcript.vtt")
    writers.write_transcript_json(segments, meta, out_dir / "transcript.json")
    writers.write_summary(text, out_dir / "summary.md")
    writers.write_keywords(text, out_dir / "keywords.md")
    writers.write_mindmap_markdown(text, out_dir / "mindmap.md")
    writers.write_mindmap_mermaid(text, out_dir / "mindmap.mmd")
    writers.write_report(
        text,
        textproc.extract_keywords(text),
        textproc.summarize(text),
        (out_dir / "mindmap.md").read_text(encoding="utf-8"),
        out_dir / "report.md",
        meta,
    )

    print("\n--- Written files ---")
    for f in sorted(out_dir.iterdir()):
        if f.is_file():
            print(f"  {f}  ({f.stat().st_size} bytes)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="audio-brief",
        description="Record or transcribe audio with Whisper and generate a summary, "
                    "mindmap, keywords and transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"audio-brief {__version__}")
    parser.add_argument("--model", default=None,
                        help=f"Whisper model: {'/'.join(MODELS)} (default: asked / base)")
    parser.add_argument("--language", default=None,
                        help="ISO 639-1/-2 language code (default: asked / auto)")
    parser.add_argument("--out", "--output", dest="out", default=None,
                        help="Output directory (default: <input folder>/audio-brief-<session>)")
    parser.add_argument("--keep-raw", action="store_true",
                        help="Keep recording/copy of the source audio in the output dir")

    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="Record from the microphone and process")
    p_rec.add_argument("duration", type=int, nargs="?", default=60,
                       help="Recording length in seconds (default 60)")

    p_tr = sub.add_parser("transcribe", help="Transcribe an existing audio file")
    p_tr.add_argument("audio", help="Path to an audio file (mp3, wav, m4a, ... )")

    args = parser.parse_args(argv)

    language = args.language
    if language is not None and not LANG_RE.match(language):
        sys.exit(f"Invalid --language '{language}': expected a 2-3 letter ISO code")
    if language is None:
        language = _ask_language()

    model_name = args.model
    if model_name is None:
        model_name = _ask_model("base")
    if model_name not in MODELS:
        sys.exit(f"Model '{model_name}' not in {', '.join(MODELS)}")

    audio: Path
    if args.command == "record":
        raw = recorder.record(args.duration)
        audio = raw
    else:
        audio = _load_audio_path(args.audio)

    # Default output location: for recordings, the current directory; for
    # existing files, the folder containing the audio (unless it's /tmp).
    if args.command == "record":
        base_dir = Path.cwd()
    else:
        base_dir = audio.parent
        if base_dir == Path("/tmp"):
            base_dir = Path.cwd()
    out_dir = Path(args.out) if args.out else base_dir / f"audio-brief-{_timestamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "record" and args.keep_raw:
        kept = out_dir / audio.name
        shutil.copy2(audio, kept)
        audio = kept

    try:
        _process(audio, model_name, language, out_dir)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()