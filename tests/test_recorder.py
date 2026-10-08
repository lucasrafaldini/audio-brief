"""Tests for audio_brief.recorder command building (no mic needed)."""

from pathlib import Path

import pytest

from audio_brief import recorder


def test_cmd_arecord():
    cmd = recorder._cmd_for("arecord", 16000, 10, Path("/tmp/x.wav"))
    assert cmd[:3] == ["arecord", "-f", "S16_LE"]
    assert "-d" in cmd and "10" in cmd


def test_cmd_unknown_backend():
    with pytest.raises(SystemExit):
        recorder._cmd_for("nope", 16000, 10, Path("/tmp/x.wav"))


def test_record_rejects_bad_duration(tmp_path):
    with pytest.raises(SystemExit):
        recorder.record(0, out_path=tmp_path / "x.wav")


def test_backend_status_keys():
    status = recorder.backend_status()
    assert set(status) == set(recorder.BACKENDS)
    assert all(isinstance(v, bool) for v in status.values())
