"""Speech-recognition engines (audio_brief/asr.py) and the --engine option.

Real-engine tests need PocketSphinx (pip install 'audio-brief[pocketsphinx]');
without it they are skipped with that reason.
"""

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from audio_brief import asr, cli

DATA = Path(__file__).with_name("data")
WAV = DATA / "librivox_sense_and_sensibility_0880.wav"
REFERENCE = (DATA / "librivox_sense_and_sensibility_0880.txt").read_text().strip()
needs_pocketsphinx = pytest.mark.skipif(importlib.util.find_spec("pocketsphinx") is None,
                                        reason="pocketsphinx not installed (pip install 'audio-brief[pocketsphinx]')")


def _wer(ref: str, hyp: str) -> float:
    """Word error rate via edit distance (no extra dependency)."""
    r, h = ref.split(), hyp.split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return d[len(h)] / len(r)


def test_status_lists_every_engine():
    status = asr.status()
    assert set(status) == set(asr.ENGINES)
    for available, detail in status.values():
        assert isinstance(available, bool) and detail


def test_unknown_engine_is_rejected():
    with pytest.raises(asr.EngineError):
        asr.load("nope")


def test_whisper_engine_normalises_the_result(monkeypatch):
    class Model:
        def transcribe(self, path, language=None, fp16=False, verbose=False):
            return {"text": " hi there ", "language": "en",
                    "segments": [{"start": 0.0, "end": 1.5, "text": "hi"}, {"start": 1.5, "end": 4.25, "text": "there"}]}

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=lambda name: Model()))
    out = asr.load("whisper", "tiny").transcribe("x.wav")
    assert out["text"] == "hi there"
    assert out["duration"] == 4.25  # Whisper has no duration key: taken from the last segment
    assert [s["end"] for s in out["segments"]] == [1.5, 4.25]


def test_pocketsphinx_rejects_other_languages_before_recording(monkeypatch):
    recorded = []
    monkeypatch.setattr(cli.recorder, "record", lambda d: recorded.append(d))
    with pytest.raises(SystemExit) as exc:
        cli.main(["record", "5", "--engine", "pocketsphinx", "--language", "pt"])
    assert "English model only" in str(exc.value.code)
    assert recorded == []  # failed before asking for the microphone


def test_missing_engine_gives_install_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(asr, "status", lambda: {"whisper": (True, "x"), "pocketsphinx": (False, "not installed: pip install 'audio-brief[pocketsphinx]'")})
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"\x00" * 100)
    with pytest.raises(SystemExit) as exc:
        cli.main(["transcribe", str(wav), "--engine", "pocketsphinx", "--out", str(tmp_path / "o")])
    assert "audio-brief[pocketsphinx]" in str(exc.value.code)


def test_cli_runs_any_engine_through_the_same_pipeline(monkeypatch, tmp_path, capsys):
    class Fake:
        model_name = "en-us (bundled)"

        def transcribe(self, path, language=None):
            segs = [{"start": 0.0, "end": 2.0, "text": "the budget review starts now"},
                    {"start": 2.0, "end": 5.0, "text": "the budget review covers marketing spend"}]
            return {"text": " ".join(s["text"] for s in segs), "segments": segs, "language": "en", "duration": 5.0}

    monkeypatch.setattr(asr, "status", lambda: {"whisper": (False, "-"), "pocketsphinx": (True, "5.1.1")})
    monkeypatch.setattr(asr, "load", lambda engine, model=None: Fake())
    monkeypatch.setattr(cli, "_MODEL_CACHE", {})
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"\x00" * 100)
    assert cli.main(["transcribe", str(wav), "--engine", "pocketsphinx", "--out", str(tmp_path / "o")]) == 0
    meta = json.loads((tmp_path / "o" / "run-0" / "transcript.json").read_text())["meta"]
    assert meta["engine"] == "pocketsphinx" and meta["language"] == "en" and meta["duration"] == 5.0
    assert "transcription (pocketsphinx)" in capsys.readouterr().out


@needs_pocketsphinx
def test_pocketsphinx_recognises_real_speech():
    out = asr.load("pocketsphinx").transcribe(WAV)
    assert out["language"] == "en"
    assert 2.5 <= out["duration"] <= 3.5
    assert out["segments"] and all(0 <= s["start"] < s["end"] <= out["duration"] + 0.01 for s in out["segments"])
    # PocketSphinx is far from perfect; this only guards against a broken pipeline.
    assert _wer(REFERENCE, out["text"]) <= 0.6, out["text"]


@needs_pocketsphinx
def test_pocketsphinx_reads_16k_wav_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(asr.shutil, "which", lambda name: None)
    with_ffmpeg_missing = asr.load("pocketsphinx").transcribe(WAV)
    monkeypatch.undo()
    assert with_ffmpeg_missing["text"] == asr.load("pocketsphinx").transcribe(WAV)["text"]


@needs_pocketsphinx
def test_pocketsphinx_reports_unreadable_audio(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(asr.EngineError):
        asr.load("pocketsphinx").transcribe(bad)


def test_wer_helper():
    assert _wer("a b c d", "a b c d") == 0
    assert _wer("a b c d", "a x c") == 0.5
    assert re.match(r"he was not", REFERENCE)


@needs_pocketsphinx
def test_pocketsphinx_never_drops_audio_when_vad_hears_nothing(monkeypatch):
    # Telephone audio can fool voice-activity detection. Every frame must still
    # be decoded; VAD only chooses cut points, and the length cap still cuts.
    normal = asr.load("pocketsphinx").transcribe(WAV)
    engine = asr.load("pocketsphinx")
    real_vad = engine._make_vad()

    class Deaf:
        frame_bytes, frame_length = real_vad.frame_bytes, real_vad.frame_length

        def is_speech(self, frame):
            return False

    monkeypatch.setattr(engine, "_make_vad", Deaf)
    monkeypatch.setattr(engine, "MAX_UTTERANCE_S", 1.0)
    deaf = engine.transcribe(WAV)
    assert deaf["duration"] == normal["duration"]  # the whole file was read
    assert len(deaf["segments"]) >= 2  # cut by the length cap
    assert _wer(REFERENCE, deaf["text"]) <= 0.8  # words still recognised
