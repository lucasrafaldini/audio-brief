"""Speech-recognition engines behind one interface.

* ``whisper`` (default): OpenAI Whisper. Accurate, many languages; needs
  PyTorch (1-3 GB download) and downloads model weights on first use.
* ``pocketsphinx``: CMU PocketSphinx 5, an independent, older HMM-based
  recogniser. Small (~40 MB including its English model), CPU-only and fully
  offline from the start, but English-only out of the box, less accurate, and
  without punctuation (audio-brief then analyses per speech segment).

Every engine returns the same dict: ``{"text", "segments", "language",
"duration"}``, with segments as ``{"start", "end", "text"}`` in seconds.
Accuracy and speed are measured in benchmarks/RESULTS.md.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

ENGINES = ("whisper", "pocketsphinx")
SAMPLE_RATE = 16000

INSTALL_HINT = {
    "whisper": "pip install 'audio-brief[whisper]' (or ./install.sh)",
    "pocketsphinx": "pip install 'audio-brief[pocketsphinx]' (or ./install.sh --engine pocketsphinx)",
}


class EngineError(RuntimeError):
    """An engine cannot be used (not installed, unsupported language, unreadable audio)."""


def status() -> dict[str, tuple[bool, str]]:
    """Which engines are importable, with a version or an install hint."""
    out = {}
    for name in ENGINES:
        module = "whisper" if name == "whisper" else "pocketsphinx"
        if importlib.util.find_spec(module) is None:
            out[name] = (False, f"not installed: {INSTALL_HINT[name]}")
            continue
        try:
            from importlib.metadata import version

            out[name] = (True, version("openai-whisper" if name == "whisper" else "pocketsphinx"))
        except Exception:  # pragma: no cover - metadata missing
            out[name] = (True, "installed")
    return out


def _duration_from_segments(segments: list[dict]) -> float:
    return float(segments[-1]["end"]) if segments else 0.0


class WhisperEngine:
    name = "whisper"

    def __init__(self, model_name: str = "base"):
        try:
            import whisper
        except ImportError as exc:
            raise EngineError(f"openai-whisper is not installed: {INSTALL_HINT['whisper']}") from exc
        self.model_name = model_name
        self.model = whisper.load_model(model_name)

    def transcribe(self, path: str | Path, language: str | None = None) -> dict[str, Any]:
        result = self.model.transcribe(str(path), language=language, fp16=False, verbose=False)
        segments = [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
                    for s in result.get("segments") or []]
        return {"text": result.get("text", "").strip(), "segments": segments,
                "language": result.get("language", language),
                "duration": float(result.get("duration") or _duration_from_segments(segments))}


class PocketSphinxEngine:
    name = "pocketsphinx"
    languages = ("en",)

    def __init__(self, model_name: str | None = None):
        try:
            from pocketsphinx import Decoder
        except ImportError as exc:
            raise EngineError(f"pocketsphinx is not installed: {INSTALL_HINT['pocketsphinx']}") from exc
        # The default configuration uses the US English model bundled in the package.
        self.decoder = Decoder(loglevel="FATAL")
        self.model_name = "en-us (bundled)"

    def _pcm_stream(self, path: Path):
        """16 kHz mono 16-bit PCM: via ffmpeg (any format), or directly from such a WAV."""
        if shutil.which("ffmpeg"):
            proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-nostdin", "-i", str(path),
                                     "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return proc.stdout, proc
        try:
            wav = wave.open(str(path), "rb")
        except (wave.Error, OSError) as exc:
            raise EngineError("ffmpeg is needed to read this audio file (install ffmpeg)") from exc
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise EngineError("ffmpeg is needed to convert this audio to 16 kHz mono (install ffmpeg)")
        return _WaveReader(wav), None

    # Utterances end at a pause of PAUSE_S seconds, or after MAX_UTTERANCE_S at
    # the latest. Voice-activity detection only chooses where to cut: every
    # frame is decoded, so a VAD that misses speech (telephone audio, noise)
    # cannot drop words. Each utterance is buffered (at most 20 s = 640 KB) and
    # decoded as a whole, which lets PocketSphinx normalise it over the full
    # utterance (more accurate than live decoding); the cap bounds memory.
    PAUSE_S = 0.5
    MAX_UTTERANCE_S = 20.0

    def _make_vad(self):
        from pocketsphinx import Vad

        return Vad(Vad.LOOSE, SAMPLE_RATE)

    def transcribe(self, path: str | Path, language: str | None = None) -> dict[str, Any]:
        if language and language.lower() not in self.languages:
            raise EngineError(f"PocketSphinx ships an English model only (got --language {language}); "
                              "use --engine whisper for other languages")
        stream, proc = self._pcm_stream(Path(path))
        vad = self._make_vad()
        frame_bytes, frame_s = vad.frame_bytes, vad.frame_length
        pause_frames = int(round(self.PAUSE_S / frame_s))
        max_frames = int(round(self.MAX_UTTERANCE_S / frame_s))
        segments: list[dict] = []
        dec = self.decoder
        n = utt_start = silent = 0
        in_utt = heard = False
        buf = bytearray()

        def finish(end_frame: int) -> None:
            nonlocal in_utt
            dec.start_utt()
            dec.process_raw(bytes(buf), False, True)
            dec.end_utt()
            buf.clear()
            in_utt = False
            hyp = dec.hyp()
            if hyp and hyp.hypstr.strip():
                segments.append({"start": round(utt_start * frame_s, 2), "end": round(end_frame * frame_s, 2),
                                 "text": hyp.hypstr.strip()})

        try:
            while True:
                frame = stream.read(frame_bytes)
                if not frame:
                    break
                if len(frame) < frame_bytes:
                    frame += b"\0" * (frame_bytes - len(frame))
                speech = vad.is_speech(frame)
                if not in_utt:
                    in_utt, utt_start, silent, heard = True, n, 0, False
                buf.extend(frame)
                n += 1
                heard = heard or speech
                silent = 0 if speech else silent + 1
                if (heard and silent >= pause_frames) or n - utt_start >= max_frames:
                    finish(n)
            if in_utt:
                finish(n)
        finally:
            if proc is not None:
                proc.stdout.close()
                err = proc.stderr.read().decode("utf-8", "replace").strip()
                if proc.wait() != 0:
                    raise EngineError(f"ffmpeg could not read {path}: {err}")
        return {"text": " ".join(s["text"] for s in segments), "segments": segments,
                "language": "en", "duration": round(n * frame_s, 2)}


class _WaveReader:
    """File-like ``read(n)`` over a wave file's frames (for the no-ffmpeg path)."""

    def __init__(self, wav: wave.Wave_read):
        self.wav = wav

    def read(self, n: int) -> bytes:
        return self.wav.readframes(n // 2)


def load(engine: str, model_name: str | None = None):
    if engine == "whisper":
        return WhisperEngine(model_name or "base")
    if engine == "pocketsphinx":
        return PocketSphinxEngine(model_name)
    raise EngineError(f"unknown engine {engine!r} (choose from: {', '.join(ENGINES)})")
