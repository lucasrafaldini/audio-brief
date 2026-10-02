"""Command-line interface for audio-brief.

Record or transcribe audio with Whisper and generate a summary, mindmap,
keywords and transcripts.

Usage:
    audio-brief record [seconds] [--model base] [--language en]
    audio-brief transcribe <file> [file2 ...] [--jobs N] [--model base] [--language en]
    audio-brief --version
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import re
import shutil
import sys
from pathlib import Path

from . import __version__
from . import recorder, writers

MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
LANG_RE = re.compile(r"^[a-zA-Z]{2,3}$")


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask_language() -> str | None:
    if not _interactive():
        return None  # non-interactive (piped/CI): auto-detect
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


def _ask_model(default: str = "base") -> str:
    if not _interactive():
        return default
    print(
        f"\nWhisper model? [{'/'.join(MODELS)}]\n"
        "Bigger = more precise but much slower (CPU). 'base' is a good default."
    )
    while True:
        ans = input(f"model [{default}]: ").strip().lower() or default
        if ans in MODELS:
            return ans
        print(f"  '{ans}' is not valid. Choose one of: {', '.join(MODELS)}")


def _output_dir(out_dir_base: Path, audio: Path, idx: int | None = None) -> Path:
    """Create a unique output folder per audio file.

    - If idx is given (sequential mode), use <base>/run-<idx>/.
    - Otherwise (parallel / single mode), use a hash of the file path.
    """
    out_path = (
        out_dir_base / f"run-{idx}"
        if idx is not None
        else out_dir_base / f"hash-{hashlib.sha1(str(audio.resolve()).encode()).hexdigest()[:8]}"
    )
    out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def transcribe_and_write(
    audio_path: str,
    model_name: str,
    language: str | None,
    out_path: Path,
) -> None:
    """Transcribe one audio file and write all output artifacts."""
    try:
        import whisper
    except ImportError:
        sys.exit(
            "openai-whisper is not installed. Run ./install.sh or "
            "`pip install openai-whisper` first."
        )

    from . import textproc

    model = whisper.load_model(model_name)
    audio = Path(audio_path)
    print(f"\nTranscribing {audio.name} (model: {model_name}, language: {language or 'auto-detect'}) ...")

    result = model.transcribe(str(audio), language=language, fp16=False, verbose=False)
    text = result.get("text", "").strip()
    if not text:
        print("WARNING: Whisper returned no text.")

    segments = result.get("segments") or []
    meta = {
        "source": str(audio),
        "model": model_name,
        "language": result.get("language", language),
        "duration": result.get("duration", 0.0),
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    out_path.mkdir(parents=True, exist_ok=True)
    writers.write_transcript_txt(segments, out_path / "transcript.txt")
    writers.write_transcript_srt(segments, out_path / "transcript.srt")
    writers.write_transcript_vtt(segments, out_path / "transcript.vtt")
    writers.write_transcript_json(segments, meta, out_path / "transcript.json")
    writers.write_summary(text, out_path / "summary.md")
    writers.write_keywords(text, out_path / "keywords.md")
    writers.write_mindmap_markdown(text, out_path / "mindmap.md")
    writers.write_mindmap_mermaid(text, out_path / "mindmap.mmd")
    writers.write_report(
        text,
        textproc.extract_keywords(text),
        textproc.summarize(text),
        (out_path / "mindmap.md").read_text(encoding="utf-8"),
        out_path / "report.md",
        meta,
    )

    print(f"\n--- Written to {out_path} ---")
    for f in sorted(out_path.iterdir()):
        if f.is_file():
            print(f"  {f}  ({f.stat().st_size} bytes)")


def transcribe_single(
    audio_path: str,
    model_name: str,
    language: str | None,
    out_dir_base: Path,
    idx: int | None = None,
) -> None:
    """Transcribe one audio file into its own subfolder of out_dir_base."""
    audio = Path(audio_path)
    out_path = _output_dir(out_dir_base, audio, idx)
    transcribe_and_write(audio_path, model_name, language, out_path)


def _add_common_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=None, choices=MODELS,
                   help=f"Whisper model (default: asked / base)")
    p.add_argument("--language", default=None,
                   help="ISO 639-1/-2 language code (default: asked / auto)")
    p.add_argument("--out", "--output", dest="out", default=None,
                   help="Output directory (default: audio-brief-<timestamp>/ under cwd)")


def _resolve_language(value: str | None) -> str | None:
    if value is None:
        return _ask_language()
    if not LANG_RE.match(value):
        sys.exit(f"Invalid --language '{value}': expected a 2-3 letter ISO code")
    return value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="audio-brief",
        description="Record or transcribe audio with Whisper and generate a summary, "
                    "mindmap, keywords and transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"audio-brief {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="Record from the microphone and process")
    p_rec.add_argument("duration", type=int, nargs="?", default=60,
                       help="Recording length in seconds (default 60)")
    p_rec.add_argument("--keep-raw", action="store_true",
                       help="Keep the raw recording inside the output folder")
    _add_common_options(p_rec)

    p_tr = sub.add_parser("transcribe", help="Transcribe one or more audio files")
    p_tr.add_argument("audio", nargs="+", help="Path(s) to audio file(s)")
    p_tr.add_argument("--jobs", type=int, default=1,
                      help="Number of parallel transcriptions (default: 1). "
                           "Use >1 for multiprocessing (each loads its own model).")
    _add_common_options(p_tr)

    args = parser.parse_args(argv)

    language = _resolve_language(args.language)
    model_name = args.model if args.model else _ask_model("base")

    out_dir_base = (
        Path(args.out).expanduser()
        if args.out
        else Path.cwd() / f"audio-brief-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    out_dir_base.mkdir(parents=True, exist_ok=True)

    if args.command == "record":
        raw = recorder.record(args.duration)
        try:
            if args.keep_raw:
                shutil.copy2(raw, out_dir_base / raw.name)
            out_path = out_dir_base / raw.stem
            transcribe_and_write(str(raw), model_name, language, out_path)
        finally:
            if not args.keep_raw:
                try:
                    raw.unlink()
                except OSError:
                    pass
        return

    # ----- transcribe -----
    audio_files = [Path(a).expanduser() for a in args.audio]
    for p in audio_files:
        if not p.is_file():
            sys.exit(f"Cannot find audio file: {p}")

    n_jobs = max(1, args.jobs)
    if n_jobs == 1:
        for i, audio in enumerate(audio_files):
            print(f"\n[{i+1}/{len(audio_files)}]", end=" ")
            transcribe_single(str(audio), model_name, language, out_dir_base, idx=i)
    else:
        print(f"\nStarting {n_jobs} parallel transcriptions (jobs={n_jobs}) …")
        with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = [
                executor.submit(transcribe_single, str(audio), model_name, language, out_dir_base, None)
                for audio in audio_files
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    sys.stderr.write(f"Transcription worker error: {e}\n")
        print("\nAll transcriptions finished.")


if __name__ == "__main__":
    main()
