"""Command-line interface for audio-brief.

Record or transcribe audio with Whisper or PocketSphinx and generate a summary,
mindmap, keywords and transcripts.

Usage:
    audio-brief record [seconds] [--engine E] [--model base] [--language en] [--min-chars N]
    audio-brief transcribe <file> [file2 ...] [--jobs N] [--engine E] [--model base] [--language en] [--min-chars N]
    audio-brief doctor
    audio-brief --version
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import platform
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from . import asr, parallel, recorder, writers

MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
LANG_RE = re.compile(r"^[a-zA-Z]{2,3}$")

_MODEL_CACHE: dict[tuple[str, str], Any] = {}
DEFAULT_ENGINE = os.environ.get("AUDIO_BRIEF_ENGINE", "whisper")


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


def _get_model(model_name: str, engine: str = "whisper") -> Any:
    """Load a speech-recognition engine once per process (cached by engine + model)."""
    key = (engine, model_name if engine == "whisper" else "")
    if key not in _MODEL_CACHE:
        label = f"Whisper model '{model_name}'" if engine == "whisper" else "PocketSphinx (bundled en-us model)"
        print(f"Loading {label} ...")
        start = time.perf_counter()
        try:
            _MODEL_CACHE[key] = asr.load(engine, model_name)
        except asr.EngineError as exc:
            sys.exit(str(exc))
        print(f"  loaded in {time.perf_counter() - start:.1f}s")
    return _MODEL_CACHE[key]


def _output_dir(out_dir_base: Path, audio: Path, idx: int | None = None) -> Path:
    """Create a unique output folder per audio file.

    - If idx is given, use <base>/run-<idx>/ (the CLI always passes the file's
      position, in sequential and parallel runs alike).
    - Otherwise (API callers of transcribe_single without an index), use a hash
      of the file path.
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
    summary_n: int = 8,
    keywords_n: int = 15,
    model: Any = None,
    min_chars: int = 20,
    engine: str = "whisper",
) -> Path:
    """Transcribe one audio file and write all output artifacts.

    Returns the output directory.
    """
    model = model if model is not None else _get_model(model_name, engine)
    audio = Path(audio_path)
    what = f"model: {model_name}" if engine == "whisper" else f"engine: {engine}"
    print(f"\nTranscribing {audio.name} ({what}, language: {language or 'auto-detect'}) ...")

    start = time.perf_counter()
    try:
        result = model.transcribe(str(audio), language=language)
    except asr.EngineError as exc:
        sys.exit(str(exc))
    transcribe_s = time.perf_counter() - start
    label = model_name if engine == "whisper" else getattr(model, "model_name", engine)
    return write_outputs(audio, result, transcribe_s, engine, label, language, out_path,
                         summary_n=summary_n, keywords_n=keywords_n, min_chars=min_chars)


def write_outputs(audio: Path, result: dict, transcribe_s: float, engine: str, model_label: str,
                  language: str | None, out_path: Path, summary_n: int = 8, keywords_n: int = 15,
                  min_chars: int = 20, quiet: bool = False) -> Path:
    """Analyse a transcription result and write every artifact (shared by the
    sequential and the parallel paths). Returns the output directory."""
    text = result.get("text", "").strip()
    if not text:
        print(f"WARNING: {engine} returned no text for {audio.name}.")

    segments = result.get("segments") or []
    meta = {
        "source": str(audio),
        "engine": engine,
        "model": model_label,
        "language": result.get("language", language),
        "duration": result.get("duration") or (segments[-1]["end"] if segments else 0.0),
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    report: dict = {}
    written = writers.write_all(
        text, segments, meta, out_path,
        summary_n=summary_n, keywords_n=keywords_n, min_char_length=min_chars, report=report,
    )
    if quiet:
        print(f"    -> {out_path} ({len(written)} files; analysis + writing {1000 * sum(report['timings'].values()):.0f} ms)")
    else:
        print(f"\n--- Written to {out_path} ---")
        for f in sorted(written):
            print(f"  {f}  ({f.stat().st_size} bytes)")
        print(format_report(report, transcribe_s, meta.get("duration") or 0.0, engine))
    return out_path


def format_report(report: dict, transcribe_s: float, audio_s: float, engine: str = "whisper") -> str:
    """Human-readable processing report: what ran, on how much text, how long it took."""
    timings = report.get("timings", {})
    speed = f" ({audio_s / transcribe_s:.1f}x real time)" if transcribe_s > 0 and audio_s > 0 else ""
    analysis_s = sum(timings.values())
    lines = [
        "\n--- Processing report ---",
        f"  transcription ({engine}): {transcribe_s:.1f}s for {audio_s:.0f}s of audio{speed}",
        f"  text: {report.get('words', 0):,} words in {report.get('units', 0):,} "
        f"{report.get('unit_kind', 'sentences')}"
        + (" (transcript had little punctuation: analysed per speech segment)"
           if report.get("unit_kind") == "segments" else ""),
        f"  found: {report.get('topics', 0)} top-level topics, "
        f"{report.get('mindmap_branches', 0)} mind-map branches, {report.get('files', 0)} files",
        "  analysis + writing: " + f"{analysis_s:.2f}s  ("
        + ", ".join(f"{stage} {sec * 1000:.0f} ms" for stage, sec in timings.items()) + ")",
    ]
    return "\n".join(lines)


def transcribe_single(
    audio_path: str,
    model_name: str,
    language: str | None,
    out_dir_base: Path,
    idx: int | None = None,
    summary_n: int = 8,
    keywords_n: int = 15,
    model: Any = None,
    min_chars: int = 20,
    engine: str = "whisper",
) -> None:
    """Transcribe one audio file into its own subfolder of out_dir_base."""
    audio = Path(audio_path)
    out_path = _output_dir(out_dir_base, audio, idx)
    transcribe_and_write(
        audio_path, model_name, language, out_path,
        summary_n=summary_n, keywords_n=keywords_n, model=model, min_chars=min_chars, engine=engine,
    )


def cmd_doctor() -> int:
    """Check the environment: Python, Whisper, recording backends."""
    ok = True
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")

    engines = asr.status()
    for name, (available, detail) in engines.items():
        print(f"engine '{name}': {'OK' if available else 'missing'} ({detail})")
    if not any(available for available, _ in engines.values()):
        print("No speech-recognition engine installed: run ./install.sh")
        ok = False
    if not shutil.which("ffmpeg"):
        print("ffmpeg: missing (Whisper and PocketSphinx need it to read audio files)")

    status = recorder.backend_status()
    for backend, available in status.items():
        print(f"recorder '{backend}': {'OK' if available else 'missing'}")
    if not any(status.values()):
        print("No recording backend found: 'record' will fail. Install ffmpeg.")
        ok = False

    if platform.system() == "Darwin":
        devices = recorder.list_devices()
        if devices:
            print("\nmacOS audio devices (ffmpeg avfoundation):")
            print(devices)
        else:
            print("\nCould not list macOS audio devices (is ffmpeg installed?)")

    print(f"\nWhisper models: {', '.join(MODELS)} (downloaded on first use); "
          "PocketSphinx: bundled US English model")
    print("\nDoctor:", "ALL OK" if ok else "ISSUES FOUND")
    return 0 if ok else 1


def _add_common_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", default=DEFAULT_ENGINE, choices=asr.ENGINES,
                   help="Speech recognition: whisper (accurate, many languages, large) or "
                        "pocketsphinx (small, offline, English only, less accurate). "
                        "Default: whisper, or $AUDIO_BRIEF_ENGINE")
    p.add_argument("--model", default=None, choices=MODELS,
                   help="Whisper model (default: asked / base); ignored by pocketsphinx")
    p.add_argument("--language", default=None,
                   help="ISO 639-1/-2 language code (default: asked / auto)")
    p.add_argument("--out", "--output", dest="out", default=None,
                   help="Output directory (default: audio-brief-<timestamp>/ under cwd)")
    p.add_argument("--summary-n", type=int, default=8, metavar="N",
                   help="Max sentences in the summary (default: 8)")
    p.add_argument("--keywords-n", type=int, default=15, metavar="N",
                   help="Max keywords extracted (default: 15)")
    p.add_argument("--min-chars", type=int, default=20, metavar="N",
                   help="Ignore sentences shorter than N characters (e.g. 'Okay.', 'lol') in the "
                        "summary, mind map and topic tree (default: 20, 0 = keep all)")


def _resolve_language(value: str | None) -> str | None:
    if value is None:
        return _ask_language()
    if not LANG_RE.match(value):
        sys.exit(f"Invalid --language '{value}': expected a 2-3 letter ISO code")
    return value


def main(argv: list[str] | None = None) -> int | None:
    parser = argparse.ArgumentParser(
        prog="audio-brief",
        description="Record or transcribe audio with Whisper or PocketSphinx and generate a summary, "
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
    p_tr.add_argument("--jobs", default="auto", metavar="N|auto",
                      help="Worker processes for recognition (default: auto = from CPU cores, free memory "
                           "and the engine's size; 1 = one file after the other). The plan is printed first.")
    split = p_tr.add_mutually_exclusive_group()
    split.add_argument("--split-long", dest="split_long", action="store_true", default=None,
                       help="Split long files at pauses so several workers share them "
                            "(default: on for pocketsphinx, off for whisper)")
    split.add_argument("--no-split-long", dest="split_long", action="store_false")
    _add_common_options(p_tr)

    sub.add_parser("doctor", help="Check environment (Python, Whisper, recording backends)")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor()

    engine = args.engine
    if engine == "pocketsphinx":
        if args.language and args.language.lower() != "en":
            sys.exit(f"PocketSphinx ships an English model only (got --language {args.language}); "
                     "use --engine whisper for other languages")
        language = "en"
        model_name = "en-us"
        available, detail = asr.status()["pocketsphinx"]
        if not available:
            sys.exit(f"PocketSphinx is {detail}")
    else:
        language = _resolve_language(args.language)
        model_name = args.model if args.model else _ask_model("base")
    if args.summary_n < 1:
        sys.exit("--summary-n must be >= 1")
    if args.keywords_n < 1:
        sys.exit("--keywords-n must be >= 1")
    if args.min_chars < 0:
        sys.exit("--min-chars must be >= 0")

    if args.command == "transcribe":  # validate before creating any output folder
        audio_files = [Path(a).expanduser() for a in args.audio]
        for p in audio_files:
            if not p.is_file():
                sys.exit(f"Cannot find audio file: {p}")
        if args.jobs != "auto" and not (str(args.jobs).isdigit() and int(args.jobs) >= 1):
            sys.exit("--jobs must be a positive number or 'auto'")

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
            transcribe_and_write(
                str(raw), model_name, language, out_path,
                summary_n=args.summary_n, keywords_n=args.keywords_n, min_chars=args.min_chars,
                engine=engine,
            )
        finally:
            if not args.keep_raw:
                try:
                    raw.unlink()
                except OSError:
                    pass
        return 0

    # ----- transcribe -----
    plan = parallel.make_plan(audio_files, engine, model_name if engine == "whisper" else None,
                              jobs=args.jobs, split=args.split_long)
    options = {"summary_n": args.summary_n, "keywords_n": args.keywords_n, "min_chars": args.min_chars}
    if plan.workers == 1 and len(plan.units) == len(audio_files):
        model = _get_model(model_name, engine)  # load once, reuse for all files
        for i, audio in enumerate(audio_files):
            print(f"\n[{i+1}/{len(audio_files)}]", end=" ")
            transcribe_single(
                str(audio), model_name, language, out_dir_base, idx=i,
                summary_n=args.summary_n, keywords_n=args.keywords_n, model=model,
                min_chars=args.min_chars, engine=engine,
            )
        return 0

    print("\n" + plan.describe(audio_files, engine))
    label = model_name if engine == "whisper" else "en-us (bundled)"

    def on_file_done(i: int, result: dict, seconds: float) -> None:
        out_path = _output_dir(out_dir_base, audio_files[i], i)
        write_outputs(audio_files[i], result, seconds, engine, label, language, out_path, quiet=True, **options)

    outcome = parallel.run(plan, audio_files, engine, model_name if engine == "whisper" else None,
                           language, on_file_done)
    print(parallel.summary(outcome, plan))
    for i, err in outcome.failed.items():
        sys.stderr.write(f"  failed: {audio_files[i]}: {err}\n")
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    sys.exit(main())
