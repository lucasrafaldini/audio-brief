"""Tests for audio_brief.writers (no Whisper needed)."""

from audio_brief import textproc, writers
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
        "keywords.md", "mindmap.md", "mindmap.mmd", "obsidian.md", "report.html",
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


# --- Obsidian note ----------------------------------------------------------

def _obsidian(tmp_path, text=SAMPLE_EN, summary=None, keywords=None, **kw):
    summary = ["First key point of the talk.", "Second key point."] if summary is None else summary
    keywords = [("whisper", 5), ("audio brief", 4), ("keywords", 2)] if keywords is None else keywords
    path = writers.write_obsidian_note(tmp_path, text, summary, keywords, **kw)
    return path, path.read_text(encoding="utf-8")


def test_obsidian_note_written_to_output_dir(tmp_path):
    out = tmp_path / "nested" / "dir"
    path, _ = _obsidian(out)
    assert path == out / "obsidian.md"
    assert path.is_file()


def test_obsidian_summary_callout(tmp_path):
    _, content = _obsidian(tmp_path)
    lines = content.splitlines()
    start = lines.index("> [!summary] Summary")
    assert lines[start + 1] == "> 1. First key point of the talk."
    assert lines[start + 2] == "> 2. Second key point."


def test_obsidian_keywords_are_wikilinks(tmp_path):
    _, content = _obsidian(tmp_path)
    assert "[[whisper]] · [[audio brief]] · [[keywords]]" in content


def test_obsidian_max_links_limits_top_keywords(tmp_path):
    kws = [(f"topic{i}", 10 - i) for i in range(10)]
    _, content = _obsidian(tmp_path, keywords=kws, max_links=3)
    assert "[[topic0]] · [[topic1]] · [[topic2]]" in content
    assert "[[topic3]]" not in content


def test_obsidian_wikilinks_sanitized_and_deduplicated(tmp_path):
    kws = [("a|b#c", 3), ("[[x]]", 2), ("a b c", 1), ("###", 1)]
    _, content = _obsidian(tmp_path, keywords=kws)
    kw_line = content.split("## Keywords\n\n", 1)[1].splitlines()[0]
    assert kw_line == "[[a b c]] · [[x]]"


def test_obsidian_accepts_plain_string_keywords(tmp_path):
    _, content = _obsidian(tmp_path, keywords=["alpha", "beta"])
    assert "[[alpha]] · [[beta]]" in content


def test_obsidian_transcript_stays_inside_callout(tmp_path):
    _, content = _obsidian(tmp_path, text="First paragraph.\n\nSecond paragraph.")
    after = content.split("> [!quote]- Transcript\n", 1)[1]
    assert after == "> First paragraph.\n>\n> Second paragraph.\n"


def test_obsidian_multiline_summary_sentence_stays_in_callout(tmp_path):
    _, content = _obsidian(tmp_path, summary=["line one\nline two"])
    assert "> 1. line one line two" in content


def test_obsidian_empty_inputs(tmp_path):
    _, content = _obsidian(tmp_path, text="", summary=[], keywords=[])
    assert "> _No summary could be extracted._" in content
    assert "_No keywords found._" in content
    assert "> _Empty transcript._" in content


def test_write_all_obsidian_matches_report_summary(tmp_path):
    meta = {"source": "test.wav", "model": "base", "language": "en", "duration": 1}
    writers.write_all(SAMPLE_EN, SAMPLE_SEGMENTS, meta, tmp_path, summary_n=3, keywords_n=5)
    content = (tmp_path / "obsidian.md").read_text(encoding="utf-8")
    for s in textproc.summarize(SAMPLE_EN, max_sentences=3):
        assert s in content
    for word, _ in textproc.extract_keywords(SAMPLE_EN, n=5):
        assert f"[[{word}]]" in content


def test_obsidian_topics_section(tmp_path):
    from tests.conftest import SAMPLE_MEETING

    _, content = _obsidian(tmp_path, text=SAMPLE_MEETING)
    section = content.split("## Topics\n\n", 1)[1].split("\n\n", 1)[0].splitlines()
    first_topic = {line.strip("- ").split("]]")[0].strip("[") for line in section[:2]}
    assert first_topic == {"customer feedback", "onboarding"}  # one topic, either can name it
    assert section[1].startswith("  - [[")  # the other is nested under it
    assert "- [[bank api]] (4)" in section and "- [[data pipeline]] (4)" in section
    assert content.index("## Keywords") < content.index("## Topics") < content.index("> [!quote]-")


def test_obsidian_topic_children_are_indented(tmp_path):
    from tests.conftest import SAMPLE_MEETING

    _, content = _obsidian(tmp_path, text=SAMPLE_MEETING)
    assert "- [[mobile app]] (3)\n  - [[release date]] (3)\n" in content


def test_topic_lines_format_timestamps():
    node = textproc.TopicNode("rent", 18, times=[65.0, 252.4, 570.0, 900.0], children=[
        textproc.TopicNode("bank api", 4, times=[3725.0]),
        textproc.TopicNode("bill", 2),
    ])
    assert writers._topic_lines([node]) == [
        "- [[rent]] (18) · 00:01:05 · 00:04:12 · 00:09:30 …",
        "  - [[bank api]] (4) · 01:02:05",
        "  - [[bill]] (2)",
    ]


def test_obsidian_no_topics_message(tmp_path):
    _, content = _obsidian(tmp_path, text="Short.")
    assert "## Topics\n\n_No recurring topics found._\n" in content


# --- write_all computes once and forwards min_char_length --------------------------

def _spy(monkeypatch, name):
    calls = []
    real = getattr(textproc, name)

    def wrapper(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(textproc, name, wrapper)
    return calls


def test_write_all_computes_each_analysis_once(tmp_path, monkeypatch):
    spies = {n: _spy(monkeypatch, n) for n in ("summarize", "extract_keywords", "build_mindmap", "topic_tree")}
    writers.write_all(SAMPLE_EN, SAMPLE_SEGMENTS, {}, tmp_path)
    assert {n: len(c) for n, c in spies.items()} == {
        "summarize": 1, "extract_keywords": 1, "build_mindmap": 1, "topic_tree": 1,
    }


def test_write_all_forwards_min_char_length(tmp_path, monkeypatch):
    spies = {n: _spy(monkeypatch, n) for n in ("summarize", "build_mindmap", "topic_tree")}
    writers.write_all(SAMPLE_EN, SAMPLE_SEGMENTS, {}, tmp_path, min_char_length=7)
    assert all(c[0]["min_char_length"] == 7 for c in spies.values())


def test_write_all_artifacts_share_the_same_analysis(tmp_path):
    writers.write_all(SAMPLE_EN, SAMPLE_SEGMENTS, {}, tmp_path, summary_n=3, keywords_n=5)
    summary = textproc.summarize(SAMPLE_EN, max_sentences=3)
    summary_md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert [f"{i}. {s}" for i, s in enumerate(summary, 1)] == summary_md.splitlines()[2:]
    keywords_md = (tmp_path / "keywords.md").read_text(encoding="utf-8")
    assert keywords_md.count("\n- ") == 5
    mm = (tmp_path / "mindmap.md").read_text(encoding="utf-8")
    mmd = (tmp_path / "mindmap.mmd").read_text(encoding="utf-8")
    assert mm.count("\n## ") == sum(1 for line in mmd.splitlines() if "ROOT --> " in line)


def test_mindmap_writers_still_work_standalone(tmp_path):
    writers.write_mindmap_markdown(SAMPLE_EN, tmp_path / "m.md")
    writers.write_mindmap_mermaid(SAMPLE_EN, tmp_path / "m.mmd")
    writers.write_summary(SAMPLE_EN, tmp_path / "s.md")
    writers.write_keywords(SAMPLE_EN, tmp_path / "k.md")
    assert (tmp_path / "m.md").read_text(encoding="utf-8").startswith("# Audio mindmap")
    assert (tmp_path / "m.mmd").read_text(encoding="utf-8").startswith("graph TD")


def test_keywords_md_shows_real_counts(tmp_path):
    from tests.conftest import SAMPLE_MEETING

    writers.write_keywords(SAMPLE_MEETING, tmp_path / "k.md")
    assert "- bank api  (4)" in (tmp_path / "k.md").read_text(encoding="utf-8")


def test_write_all_fills_the_processing_report(tmp_path):
    from tests.conftest import make_conversation

    c = make_conversation(400, punct=False)
    report = {}
    written = writers.write_all(c.text, c.segments, {}, tmp_path, report=report)
    assert list(report["timings"])[-1] == "writing files"
    assert {"specificity", "topic tree", "mind map"} <= set(report["timings"])
    assert report["unit_kind"] == "segments" and report["units"] == len(c.segments)
    assert report["files"] == len(written) == 11
    assert report["words"] > 0 and report["topics"] >= 1 and report["mindmap_branches"] >= 1
