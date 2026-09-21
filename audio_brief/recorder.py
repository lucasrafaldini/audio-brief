"""Recording of audio from the microphone (Linux and macOS).

Backends, in order of preference:
  * arecord  (Linux / ALSA)
  * ffmpeg   (macOS via avfoundation, or Linux via alsa)
  * rec      (sox, if installed)

You can force a backend with the AUDIO_BRIEF_RECORDER env var
(e.g. AUDIO_BRIEF_RECORDER=ffmpeg).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

BACKENDS = ("arecord", "ffmpeg", "rec")


def _available(cmd: str) -> bool:
    try:
        subprocess.run(
            [cmd, "--version"], capture_output=True, check=False, timeout=10
        )
        return True
    except OSError:
        return False


def _pick_backend() -> str:
    forced = os.environ.get("AUDIO_BRIEF_RECORDER")
    if forced:
        return forced
    if platform.system() == "Darwin":
        return "ffmpeg"
    # Linux / other
    for backend in BACKENDS:
        if _available(backend):
            return backend
    return "arecord"


def _cmd_for(backend: str, rate: int, duration: int, out_path: Path) -> list[str]:
    if backend == "arecord":
        return [
            "arecord",
            "-f", "S16_LE",
            "-c", "1",
            "-r", str(rate),
            "-d", str(duration),
            str(out_path),
        ]
    if backend == "ffmpeg":
        if platform.system() == "Darwin":
            # macOS: avfoundation, default input device "0".
            input_src = os.environ.get("AUDIO_BRIEF_MIC", "0")
            fmt = "avfoundation"
        else:
            # Linux: the 'default' ALSA device.
            input_src = os.environ.get("AUDIO_BRIEF_MIC", "default")
            fmt = "alsa"
        return [
            "ffmpeg",
            "-loglevel", "error",
            "-y",
            "-f", fmt,
            "-i", input_src,
            "-t", str(duration),
            "-ac", "1",
            "-ar", str(rate),
            "-acodec", "pcm_s16le",
            str(out_path),
        ]
    if backend == "rec":
        return [
            "rec",
            "-r", str(rate),
            "-c", "1",
            "-b", "16",
            str(out_path),
            "trim", "0", str(duration),
        ]
    raise SystemExit(f"Unknown recorder backend '{backend}' (use one of: {', '.join(BACKENDS)})")


def record(duration: int, rate: int = 16000, out_path: Path | None = None) -> Path:
    """Record `duration` seconds of mono audio from the default mic.

    Returns the path to a 16-bit mono WAV file.
    """
    out_path = out_path or Path(tempfile.gettempdir()) / "audio-brief-tmp.wav"
    if out_path.exists():
        out_path.unlink()
    backend = _pick_backend()
    cmd = _cmd_for(backend, rate, duration, out_path)

    print(f"\nRecording {duration}s from mic using '{backend}' ... (Ctrl-C to stop early)")
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        pass

    if not out_path.exists() or out_path.stat().st_size < 1000:
        hint = "Make sure a microphone is connected."
        if backend == "ffmpeg" and platform.system() == "Darwin":
            hint += (
                " On macOS, list input devices with: "
                "ffmpeg -f avfoundation -list_devices true -i ''  and pick the "
                "audio input index via AUDIO_BRIEF_MIC (default 0)."
            )
        else:
            hint += " Check your default ALSA/PulseAudio input."
        sys.stderr.write(f"Recording failed. {hint}\n")
        raise SystemExit(1)

    print(f"Saved recording to {out_path}")
    return out_path