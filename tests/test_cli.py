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


# --- --min-chars ---------------------------------------------------------------------

@pytest.fixture()
def captured_write_all(monkeypatch):
    calls = []
    real = cli.writers.write_all

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(cli.writers, "write_all", spy)
    return calls


def _wav(tmp_path, name="talk.wav"):
    audio = tmp_path / name
    audio.write_bytes(b"\x00" * 2000)
    return str(audio)


BASE = ["--model", "base", "--language", "en"]


def test_min_chars_defaults_to_20(tmp_path, fake_whisper, captured_write_all):
    assert cli.main(["transcribe", _wav(tmp_path), *BASE, "--out", str(tmp_path / "o")]) == 0
    assert captured_write_all[0]["min_char_length"] == 20


def test_min_chars_forwarded_sequential(tmp_path, fake_whisper, captured_write_all):
    cli.main(["transcribe", _wav(tmp_path), *BASE, "--out", str(tmp_path / "o"), "--min-chars", "0"])
    assert captured_write_all[0]["min_char_length"] == 0


def test_min_chars_forwarded_parallel(tmp_path, fake_whisper, captured_write_all, monkeypatch):
    # Threads instead of processes so the Whisper stub applies inside the workers.
    import functools

    monkeypatch.setattr(cli.parallel, "run", functools.partial(cli.parallel.run, executor="thread"))
    files = [_wav(tmp_path, "a.wav"), _wav(tmp_path, "b.wav")]
    rc = cli.main(["transcribe", *files, *BASE, "--out", str(tmp_path / "o"), "--jobs", "2", "--min-chars", "5"])
    assert rc == 0
    assert [c["min_char_length"] for c in captured_write_all] == [5, 5]


def test_min_chars_forwarded_record(tmp_path, fake_whisper, captured_write_all, monkeypatch):
    monkeypatch.setattr(cli.recorder, "record", lambda duration: cli.Path(_wav(tmp_path, "rec.wav")))
    assert cli.main(["record", "3", *BASE, "--out", str(tmp_path / "o"), "--min-chars", "40"]) == 0
    assert captured_write_all[0]["min_char_length"] == 40


def test_min_chars_rejects_negative(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["transcribe", _wav(tmp_path), *BASE, "--min-chars", "-1"])
    assert "--min-chars" in str(exc.value.code)


def test_min_chars_changes_the_summary(tmp_path, fake_whisper):
    # The stub transcript starts with "Hello world." (12 chars).
    for n, expect in ((0, True), (20, False)):
        out = tmp_path / f"o{n}"
        cli.main(["transcribe", _wav(tmp_path), *BASE, "--out", str(out), "--min-chars", str(n)])
        summary = (out / "run-0" / "summary.md").read_text(encoding="utf-8")
        assert ("Hello world." in summary) is expect


def test_format_report_lines():
    report = {"timings": {"units": 0.001, "specificity": 0.25, "writing files": 0.05}, "words": 12345,
              "units": 800, "unit_kind": "segments", "topics": 7, "mindmap_branches": 9, "files": 11}
    text = cli.format_report(report, transcribe_s=30.0, audio_s=600.0)
    assert "transcription (whisper): 30.0s for 600s of audio (20.0x real time)" in text
    assert "12,345 words in 800 segments (transcript had little punctuation: analysed per speech segment)" in text
    assert "7 top-level topics, 9 mind-map branches, 11 files" in text
    assert "analysis + writing: 0.30s  (units 1 ms, specificity 250 ms, writing files 50 ms)" in text


def test_transcribe_prints_processing_report(tmp_path, fake_whisper, capsys):
    cli.transcribe_and_write(_wav(tmp_path), "base", "en", tmp_path / "o")
    out = capsys.readouterr().out
    assert "--- Processing report ---" in out
    assert "specificity" in out and "writing files" in out
