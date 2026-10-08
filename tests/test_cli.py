"""Tests for CLI parsing and the offline transcribe path (Whisper stubbed)."""

import sys
import types

import pytest

from audio_brief import cli


class _FakeModel:
    def __init__(self):
        self.calls = 0

    def transcribe(self, path, language=None, fp16=False, verbose=False):
        self.calls += 1
        return {
            "text": "Hello world. This is a test transcript with enough words here.",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello world."}],
            "language": language or "en",
            "duration": 1.0,
        }


@pytest.fixture()
def fake_whisper(monkeypatch):
    """Inject a stub `whisper` module so no download/torch is needed."""
    mod = types.ModuleType("whisper")
    mod.load_model = lambda name: _FakeModel()
    monkeypatch.setitem(sys.modules, "whisper", mod)
    monkeypatch.setattr(cli, "_MODEL_CACHE", {})
    return mod


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_doctor_runs_without_whisper(monkeypatch):
    monkeypatch.setitem(sys.modules, "whisper", None)
    # None in sys.modules makes `import whisper` raise ImportError.
    rc = cli.cmd_doctor()
    assert rc in (0, 1)


def test_transcribe_writes_outputs(tmp_path, fake_whisper):
    audio = tmp_path / "talk.wav"
    audio.write_bytes(b"\x00" * 2000)
    out = tmp_path / "out"
    result = cli.transcribe_and_write(str(audio), "base", "en", out)
    assert result == out
    assert (out / "report.md").exists()
    assert (out / "report.html").exists()
    assert (out / "transcript.vtt").exists()


def test_model_cached_across_files(tmp_path, fake_whisper):
    model = cli._get_model("base")
    assert cli._get_model("base") is model  # same object, no reload


def test_invalid_language_rejected():
    with pytest.raises(SystemExit):
        cli.main(["transcribe", "x.wav", "--language", "toolong!"])
