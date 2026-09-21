"""Command-line interface for audio-brief.

Record or transcribe audio with Whisper and generate a summary, mindmap,
keywords and transcripts.

Usage:
    audio-brief record <seconds>
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


def _output_dir(out_dir_base: Path, audio: Path, idx: int | None = None) -> Path:
    """Create a unique output folder per audio file.

    - If idx is given (sequential mode), use audio-brief-<ts>/<idx>/.
    - Otherwise (parallel mode), use a hash of the file path so each file
      gets its own folder inside audio-brief-<ts>/.
    """
    out_path = out_dir_base / f"run-{idx}" if idx is not None else out_dir_base / f"hash-{hashlib.sha1(str(audio.resolve()).encode()).hexdigest()[:8]}"
    out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def transcribe_single(
    audio_path: str,
    model_name: str,
    language: str | None,
    out_dir_base: Path,
    idx: int | None = None,
) -> None:
    """Transcribe one audio file.

    idx is the sequential index (for ordered output folders) or None (for
    parallel mode where we use a path hash to avoid collisions).
    """
    import whisper
    from . import textproc

    model = whisper.load_model(model_name)
    audio = Path(audio_path)
    print(f"\nTranscribing {audio.name} (model: {model_name}, language: {language or 'auto-detect'}) ...")

    result = model.transcribe(
        str(audio),
        language=language,
        fp16=False,
        verbose=False,
    )
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

    out_path = _output_dir(out_dir_base, audio, idx)
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="audio-brief",
        description="Record or transcribe audio with Whisper and generate a summary, "
                    "mindmap, keywords and transcripts.",
    )
    parser.add_argument("--version", action="version", version=f"audio-brief {__version__}")
    parser.add_argument("--model", default=None,
                        help=f"Whisper model: {'/'.join(MODELS)} (default: asked / base)")

    sub = parser.add_subparsers(dest="command", required=True)

    # ----- record subcommand -----
    p_rec = sub.add_parser("record", help="Record from the microphone and process")
    p_rec.add_argument("duration", type=int, nargs="?", default=60,
                       help="Recording length in seconds (default 60)")

    # ----- transcribe subcommand -----
    p_tr = sub.add_parser("transcribe", help="Transcribe one or more audio files")
    p_tr.add_argument("audio", nargs="+", help="Path(s) to audio file(s)")
    p_tr.add_argument("--jobs", type=int, default=1,
                        help="Number of parallel transcriptions (default: 1). "
                             "Use >1 for multiprocessing (each loads its own model).")
    p_tr.add_argument("--language", default=None,
                        help="ISO 639-1/-2 language code (default: asked / auto)")
    p_tr.add_argument("--out", "--output", dest="out", default=None,
                        help="Output directory (default: per-file under cwd)")

    args = parser.parse_args(argv)

    # Validate language if provided globally (record doesn't use it).
    if args.command == "transcribe":
        language = args.language
        if language is not None and not LANG_RE.match(language):
            sys.exit(f"Invalid --language '{language}': expected a 2-3 letter ISO code")
        if language is None:
            language = _ask_language()
        model_name = args.model if args.model else _ask_model("base")
        if model_name not in MODELS:
            sys.exit(f"Model '{model_name}' not in {', '.join(MODELS)}")

        audio_files = [Path(a).expanduser() for a in args.audio]
        for p in audio_files:
            if not p.is_file():
                sys.exit(f"Cannot find audio file: {p}")

        # Base output directory: use cwd if no --out.
        out_dir_base = Path(args.out) if args.out else Path.cwd() / f"audio-brief-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir_base.mkdir(parents=True, exist_ok=True)

        n_jobs = max(1, args.jobs)
        if n_jobs == 1:
            # Sequential: hand off an index so each gets a numbered folder.
            for i, audio in enumerate(audio_files):
                print(f"\nTranscribing {audio.name} (model: {model_name}, language: {language or 'auto-detect'}) [#{i+1}/{len(audio_files)}] ...")
                transcribe_single(str(audio), model_name, language, out_dir_base, idx=i)
        else:
            # Parallel: each worker gets a unique folder via path hash.
            print(f"\nStarting {n_jobs} parallel transcriptions (jobs={n_jobs}) …")
            with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
                futures = []
                for i, audio in enumerate(audio_files):
                    future = executor.submit(
                        transcribe_single,
                        str(audio),
                        model_name,
                        language,
                        out_dir_base,  # base dir; worker creates its own subfolder via hash
                        None,          # idx=None → parallel mode uses hash
                    )
                    futures.append(future)
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        sys.stderr.write(f"Transcription worker error: {e}\n")
            print("\nAll transcriptions finished.")

    elif args.command == "record":
        raw = recorder.record(args.duration)
        out_dir_base = Path.cwd() / f"audio-brief-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir_base.mkdir(parents=True, exist_ok=True)

        if args.keep_raw:
            shutil.copy2(raw, out_dir_base / raw.name)

        # Transcribe the recording immediately (single job, no prompt replay).
        import whisper
        model = whisper.load_model(model_name if 'model_name' in dir() else "base")
        lang_msg = language if 'language' in dir() else "auto-detect"
        # Actually re-prompt for language/model for record if not provided:
        # For simplicity, we just reuse the already-asked values from above,
        # but record has its own flow. Let me just do a quick single transcription
        # using the global language/model if they were already set, otherwise ask.
        # Since argparse doesn't carry --language/--model into record subcommand
        # easily, we just ask again here.
        language2 = _ask_language()
        if language2 is None:
            language2 = "auto"
        model_name2 = _ask_model("base")
        if model_name2 not in MODELS:
            sys.exit(f"Model '{model_name2}' not valid.")
        model = whisper.load_model(model_name2)
        lang_msg = language2 or "auto-detect"
        print(f"\nTranscribing recording (language: {lang_msg}) ...")
        result = model.transcribe(str(raw), language=language2, fp16=False, verbose=False)
        text = result.get("text", "").strip()
        segments = result.get("segments") or []
        meta = {
            "source": str(raw),
            "model": model_name2,
            "language": result.get("language", language2),
            "duration": result.get("duration", 0.0),
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        out_dir = out_dir_base / raw.stem
        out_dir.mkdir(parents=True, exist_ok=True)
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


if __name__ == "__main__":
    main()