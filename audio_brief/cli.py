"""Command-line interface for audio-brief.

Record or transcribe audio with Whisper and generate a summary, mindmap,
keywords and transcripts.

Usage:
    audio-brief record [seconds] [--model base] [--language en]
    audio-brief transcribe <file> [file2 ...] [--jobs N] [--model base] [--language en]
    audio-brief doctor
    audio-brief --version
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import recorder, writers

MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
LANG_RE = re.compile(r"^[a-zA-Z]{2,3}$")

_MODEL_CACHE: dict[str, Any] = {}


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


def _get_model(model_name: str) -> Any:
    """Load a Whisper model once per process (cached)."""
    if model_name not in _MODEL_CACHE:
        try:
            import whisper
        except ImportError:
            sys.exit(
                "openai-whisper is not installed. Run ./install.sh or "
                "`pip install openai-whisper` first."
            )
        print(f"Loading Whisper model '{model_name}' ...")
        _MODEL_CACHE[model_name] = whisper.load_model(model_name)
    return _MODEL_CACHE[model_name]


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
    summary_n: int = 8,
    keywords_n: int = 15,
    model: Any = None,
) -> Path:
    """Transcribe one audio file and write all output artifacts.

    Returns the output directory.
    """
    model = model if model is not None else _get_model(model_name)
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

    written = writers.write_all(
        text, segments, meta, out_path,
        summary_n=summary_n, keywords_n=keywords_n,
    )
    print(f"\n--- Written to {out_path} ---")
    for f in sorted(written):
        print(f"  {f}  ({f.stat().st_size} bytes)")
    return out_path


def transcribe_single(
    audio_path: str,
    model_name: str,
    language: str | None,
    out_dir_base: Path,
    idx: int | None = None,
    summary_n: int = 8,
    keywords_n: int = 15,
    model: Any = None,
) -> None:
    """Transcribe one audio file into its own subfolder of out_dir_base."""
    audio = Path(audio_path)
    out_path = _output_dir(out_dir_base, audio, idx)
    transcribe_and_write(
        audio_path, model_name, language, out_path,
        summary_n=summary_n, keywords_n=keywords_n, model=model,
    )


def cmd_doctor() -> int:
    """Check the environment: Python, Whisper, recording backends."""
    ok = True
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")

    try:
        import whisper

        print(f"whisper {whisper.__version__} installed: OK")
    except ImportError:
        print("whisper NOT installed (run ./install.sh): MISSING")
        ok = False

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

    print(f"\nWhisper models: {', '.join(MODELS)} (downloaded on first use)")
    print("\nDoctor:", "ALL OK" if ok else "ISSUES FOUND")
    return 0 if ok else 1


def _add_common_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", default=None, choices=MODELS,
                   help="Whisper model (default: asked / base)")
    p.add_argument("--language", default=None,
                   help="ISO 639-1/-2 language code (default: asked / auto)")
    p.add_argument("--out", "--output", dest="out", default=None,
                   help="Output directory (default: audio-brief-<timestamp>/ under cwd)")
    p.add_argument("--summary-n", type=int, default=8, metavar="N",
                   help="Max sentences in the summary (default: 8)")
    p.add_argument("--keywords-n", type=int, default=15, metavar="N",
                   help="Max keywords extracted (default: 15)")


def _resolve_language(value: str | None) -> str | None:
    if value is None:
        return _ask_language()
    if not LANG_RE.match(value):
        sys.exit(f"Invalid --language '{value}': expected a 2-3 letter ISO code")
    return value


def main(argv: list[str] | None = None) -> int | None:
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

    sub.add_parser("doctor", help="Check environment (Python, Whisper, recording backends)")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return cmd_doctor()

    language = _resolve_language(args.language)
    model_name = args.model if args.model else _ask_model("base")
    if args.summary_n < 1:
        sys.exit("--summary-n must be >= 1")
    if args.keywords_n < 1:
        sys.exit("--keywords-n must be >= 1")

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
                summary_n=args.summary_n, keywords_n=args.keywords_n,
            )
        finally:
            if not args.keep_raw:
                try:
                    raw.unlink()
                except OSError:
                    pass
        return 0

    # ----- transcribe -----
    audio_files = [Path(a).expanduser() for a in args.audio]
    for p in audio_files:
        if not p.is_file():
            sys.exit(f"Cannot find audio file: {p}")

    n_jobs = max(1, args.jobs)
    if n_jobs == 1:
        model = _get_model(model_name)  # load once, reuse for all files
        for i, audio in enumerate(audio_files):
            print(f"\n[{i+1}/{len(audio_files)}]", end=" ")
            transcribe_single(
                str(audio), model_name, language, out_dir_base, idx=i,
                summary_n=args.summary_n, keywords_n=args.keywords_n, model=model,
            )
    else:
        print(f"\nStarting {n_jobs} parallel transcriptions (jobs={n_jobs}) …")
        with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = [
                executor.submit(
                    transcribe_single, str(audio), model_name, language,
                    out_dir_base, None, args.summary_n, args.keywords_n, None,
                )
                for audio in audio_files
            ]
            failed = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    failed += 1
                    sys.stderr.write(f"Transcription worker error: {e}\n")
        print("\nAll transcriptions finished.")
        if failed:
            sys.stderr.write(f"{failed} file(s) failed.\n")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
