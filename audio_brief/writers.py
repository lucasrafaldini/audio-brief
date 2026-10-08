"""Writers for the various output formats generated from a transcript."""

from __future__ import annotations

import json
import time
from html import escape
from datetime import timedelta
from pathlib import Path

from . import textproc


def _hms(seconds: float) -> str:
    return str(timedelta(seconds=round(seconds)))


def _srt_ts(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{_hms(seconds).zfill(8)},{ms:03d}"


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
        out.append(f"{_srt_ts(s['start'])} --> {_srt_ts(s['end'])}")
        out.append(s["text"].strip())
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_transcript_json(segments, meta: dict, path: Path) -> None:
    payload = {"meta": meta, "segments": segments}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary(text: str, path: Path) -> None:
    sents = textproc.summarize(text)
    lines = ["# Summary", ""]
    if not sents:
        lines.append("_No summary could be extracted._")
    for i, s in enumerate(sents, 1):
        lines.append(f"{i}. {s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_keywords(text: str, path: Path) -> None:
    kws = textproc.extract_keywords(text)
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
    lines = [
        "# Audio Brief",
        "",
        f"- Source: `{meta.get('source', '?')}`",
        f"- Model: `{meta.get('model', '?')}`  Language: `{meta.get('language', '?')}`",
        f"- Duration: {_hms(meta.get('duration', 0))}  Generated: {time.strftime('%Y-%m-%d %H:%M')}",
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
    """Write an offline HTML brief, including the complete transcript."""
    def value(key: str) -> str:
        return escape(str(meta.get(key, "?")))

    keyword_items = "".join(
        f"<li>{escape(word)} <span>({count})</span></li>" for word, count in keywords
    ) or "<li>No keywords could be extracted.</li>"
    summary_items = "".join(f"<li>{escape(sentence)}</li>" for sentence in summary)
    summary_items = summary_items or "<li>No summary could be extracted.</li>"
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audio Brief — {value('source')}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ max-width: 72ch; margin: auto; padding: 2rem 1rem;
  font: 1rem/1.65 system-ui, sans-serif; }}
h1, h2 {{ line-height: 1.2; }}
header {{ border-bottom: 1px solid; padding-bottom: 1rem; }}
section {{ margin-top: 2.5rem; }}
nav {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
a {{ color: inherit; text-underline-offset: .2em; }}
pre, .transcript {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
dt {{ font-weight: 600; }}
dd {{ margin: 0 0 .5rem; overflow-wrap: anywhere; }}
.keywords {{ display: flex; flex-wrap: wrap; gap: .5rem 2rem; }}
@media print {{ nav {{ display: none; }} body {{ padding: 0; }} }}
</style>
</head>
<body>
<header>
<h1>Audio Brief</h1>
<dl><dt>Source</dt><dd>{value('source')}</dd>
<dt>Model / language</dt><dd>{value('model')} / {value('language')}</dd>
<dt>Duration</dt><dd>{escape(_hms(meta.get('duration', 0)))}</dd>
<dt>Generated</dt><dd>{value('generated')}</dd></dl>
<nav aria-label="Report sections"><a href="#summary">Summary</a>
<a href="#keywords">Keywords</a><a href="#mindmap">Mindmap</a>
<a href="#transcript">Transcript</a></nav>
</header>
<main>
<section id="summary"><h2>Summary</h2><ol>{summary_items}</ol></section>
<section id="keywords"><h2>Keywords</h2><ul class="keywords">{keyword_items}</ul></section>
<section id="mindmap"><h2>Mindmap outline</h2><pre>{escape(mindmap_md.strip())}</pre></section>
<section id="transcript"><h2>Transcript</h2><div class="transcript">{escape(text)}</div></section>
</main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
