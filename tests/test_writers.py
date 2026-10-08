"""Tests for audio_brief.writers (no Whisper needed)."""

from audio_brief import writers
from tests.conftest import SAMPLE_EN, SAMPLE_SEGMENTS


def test_hms_zero_padded():
    assert writers._hms(5) == "00:00:05"
    assert writers._hms(61.2) == "00:01:01"
    assert writers._hms(3661) == "01:01:01"


def test_vtt_uses_period_separator(tmp_path):
    dest = tmp_path / "t.vtt"
    writers.write_transcript_vtt(SAMPLE_SEGMENTS, dest)
    content = dest.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in content or ".500" in content
    assert ",500" not in content  # SRT-style commas are invalid in VTT


def test_srt_uses_comma_separator(tmp_path):
    dest = tmp_path / "t.srt"
    writers.write_transcript_srt(SAMPLE_SEGMENTS, dest)
    content = dest.read_text(encoding="utf-8")
    assert "-->" in content
    assert ",500" in content


def test_write_all_produces_every_artifact(tmp_path):
    meta = {"source": "test.wav", "model": "base", "language": "en", "duration": 61.2}
    written = writers.write_all(SAMPLE_EN, SAMPLE_SEGMENTS, meta, tmp_path)
    names = sorted(p.name for p in written)
    assert names == [
        "keywords.md", "mindmap.md", "mindmap.mmd", "report.html",
        "report.md", "summary.md", "transcript.json", "transcript.srt",
        "transcript.txt", "transcript.vtt",
    ]
    assert (tmp_path / "report.html").read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_report_html_escapes_content(tmp_path):
    meta = {"source": "<evil>.wav", "model": "base", "language": "en", "duration": 1}
    dest = tmp_path / "r.html"
    writers.write_report_html("<script>alert(1)</script>", [], [], "# mind", dest, meta)
    content = dest.read_text(encoding="utf-8")
    assert "<script>" not in content
    assert "&lt;script&gt;" in content
