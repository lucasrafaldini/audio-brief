"""Writers for the various output formats generated from a transcript."""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

from . import textproc


def _hms(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _srt_ts(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{_hms(seconds)},{ms:03d}"


def _vtt_ts(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{_hms(seconds)}.{ms:03d}"


def write_transcript_txt(segments, path: Path) -> None:
    lines = [f"[{_hms(s['start'])} - {_hms(s['end'])}] {s['text'].strip()}" for s in segments]
    path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_transcript_srt(segments, path: Path) -> None:
    out = []
    for i, s in enumerate(segments, 1):
        out.append(f"{i}")
        out.append(f"{_srt_ts(s['start'])} --> {_srt_ts(s['end'])}")
        out.append(s["text"].strip())
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_transcript_vtt(segments, path: Path) -> None:
    out = ["WEBVTT", ""]
    for s in segments:
        out.append(f"{_vtt_ts(s['start'])} --> {_vtt_ts(s['end'])}")
        out.append(s["text"].strip())
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_transcript_json(segments, meta: dict, path: Path) -> None:
    payload = {"meta": meta, "segments": segments}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary(text: str, path: Path, max_sentences: int = 8) -> None:
    sents = textproc.summarize(text, max_sentences=max_sentences)
    lines = ["# Summary", ""]
    if not sents:
        lines.append("_No summary could be extracted._")
    for i, s in enumerate(sents, 1):
        lines.append(f"{i}. {s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_keywords(text: str, path: Path, n: int = 15) -> None:
    kws = textproc.extract_keywords(text, n=n)
    lines = ["# Key topics / keywords", ""]
    for word, count in kws:
        lines.append(f"- {word}  ({count})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mindmap_markdown(text: str, path: Path) -> None:
    """Markmap-compatible Markdown mind map (# root, ## branch, ### leaf)."""
    clusters = textproc.build_mindmap(text)
    sents = textproc.sentences(text)
    lines = ["# Audio mindmap", ""]
    for cl in clusters:
        label = textproc.cluster_label(cl, sents)
        lines.append(f"## {label}")
        for i in cl.members:
            snippet = sents[i][:110]
            lines.append(f"### {snippet}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mm_text(s: str) -> str:
    s = s.replace('"', "'").replace("\n", " ")
    return s[:110]


def write_mindmap_mermaid(text: str, path: Path) -> None:
    """Mermaid flowchart mind map."""
    clusters = textproc.build_mindmap(text)
    sents = textproc.sentences(text)
    lines = ["graph TD", '    ROOT["Audio mindmap"]']
    for ci, cl in enumerate(clusters):
        label = textproc.cluster_label(cl, sents)
        lines.append(f'    C{ci}["{_mm_text(label)}"]')
        lines.append(f"    ROOT --> C{ci}")
        for i, member in enumerate(cl.members[:6]):
            lines.append(f'    C{ci}L{i}["{_mm_text(sents[member])}"]')
            lines.append(f"    C{ci} --> C{ci}L{i}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(text: str, keywords: list[tuple[str, int]], summary: list[str],
                 mindmap_md: str, path: Path, meta: dict) -> None:
    """Single self-contained Markdown report bundling all artifacts."""
    stats = textproc.stats(text)
    lines = [
        "# Audio Brief",
        "",
        f"- Source: `{meta.get('source', '?')}`",
        f"- Model: `{meta.get('model', '?')}`  Language: `{meta.get('language', '?')}`",
        f"- Duration: {_hms(meta.get('duration', 0))}  Generated: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- Words: {stats['words']}  Sentences: {stats['sentences']}  (~{stats['reading_minutes']} min read)",
        "",
        "## Keywords",
        ""
    ]
    for word, count in keywords:
        lines.append(f"- {word}")
    lines += ["", "## Summary", ""]
    for s in summary:
        lines.append(f"- {s}")
    lines += ["", "## Mindmap", "", mindmap_md.strip(), ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report_html(text: str, keywords: list[tuple[str, int]], summary: list[str],
                      mindmap_md: str, path: Path, meta: dict) -> None:
    """Self-contained HTML report (inline CSS, no external assets)."""
    stats = textproc.stats(text)
    kw_items = "\n".join(f"      <li>{html.escape(w)} <span>({c})</span></li>" for w, c in keywords)
    sum_items = "\n".join(f"      <li>{html.escape(s)}</li>" for s in summary)
    src = html.escape(str(meta.get("source", "?")))
    paragraphs = "\n".join(
        f"      <p>{html.escape(p.strip())}</p>"
        for p in text.split("\n") if p.strip()
    )
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audio Brief — {src}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  .meta {{ color: #555; font-size: .9rem; }}
  h2 {{ border-bottom: 1px solid #ddd; padding-bottom: .25rem; }}
  pre {{ background: #f6f6f6; padding: 1rem; overflow-x: auto; border-radius: 6px; }}
  li span {{ color: #777; }}
</style>
</head>
<body>
  <h1>🎧 Audio Brief</h1>
  <p class="meta">Source: {src} · Model: {html.escape(str(meta.get('model', '?')))} ·
  Language: {html.escape(str(meta.get('language', '?')))} ·
  Duration: {_hms(meta.get('duration', 0))} · Words: {stats['words']}</p>
  <h2>Keywords</h2>
  <ul>
{kw_items}
  </ul>
  <h2>Summary</h2>
  <ol>
{sum_items}
  </ol>
  <h2>Mindmap</h2>
  <pre>{html.escape(mindmap_md.strip())}</pre>
  <h2>Transcript</h2>
{paragraphs}
</body>
</html>
"""
    path.write_text(doc, encoding="utf-8")


def write_all(text: str, segments, meta: dict, out_dir: Path,
              summary_n: int = 8, keywords_n: int = 15) -> list[Path]:
    """Write every artifact once (summary/keywords computed a single time).

    Returns the list of files written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = textproc.summarize(text, max_sentences=summary_n)
    keywords = textproc.extract_keywords(text, n=keywords_n)

    paths = {
        "transcript.txt": lambda p: write_transcript_txt(segments, p),
        "transcript.srt": lambda p: write_transcript_srt(segments, p),
        "transcript.vtt": lambda p: write_transcript_vtt(segments, p),
        "transcript.json": lambda p: write_transcript_json(segments, meta, p),
        "summary.md": lambda p: write_summary(text, p, max_sentences=summary_n),
        "keywords.md": lambda p: write_keywords(text, p, n=keywords_n),
        "mindmap.md": lambda p: write_mindmap_markdown(text, p),
        "mindmap.mmd": lambda p: write_mindmap_mermaid(text, p),
    }
    written = []
    for name, fn in paths.items():
        dest = out_dir / name
        fn(dest)
        written.append(dest)

    mindmap_md = (out_dir / "mindmap.md").read_text(encoding="utf-8")
    write_report(text, keywords, summary, mindmap_md, out_dir / "report.md", meta)
    written.append(out_dir / "report.md")
    write_report_html(text, keywords, summary, mindmap_md, out_dir / "report.html", meta)
    written.append(out_dir / "report.html")
    return written
