"""Writers for the various output formats generated from a transcript."""

from __future__ import annotations

import html
import json
import re
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


def write_summary(text: str, path: Path, max_sentences: int = 8,
                  summary: list[str] | None = None) -> None:
    sents = summary if summary is not None else textproc.summarize(text, max_sentences=max_sentences)
    lines = ["# Summary", ""]
    if not sents:
        lines.append("_No summary could be extracted._")
    for i, s in enumerate(sents, 1):
        lines.append(f"{i}. {s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_keywords(text: str, path: Path, n: int = 15,
                   keywords: list[tuple[str, int]] | None = None) -> None:
    kws = keywords if keywords is not None else textproc.extract_keywords(text, n=n)
    lines = ["# Key topics / keywords", ""]
    for word, count in kws:
        lines.append(f"- {word}  ({count})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mindmap_groups(text: str, clusters, groups, units):
    """Resolve what to draw: explicit groups, plain clusters (one per branch) or a fresh analysis."""
    if groups is not None:
        return groups, (units if units is not None else textproc.sentences(text))
    if clusters is not None:
        sents = units if units is not None else textproc.sentences(text)
        return [textproc.MindmapGroup(textproc.cluster_label(c, sents), [c]) for c in clusters], sents
    analysis = textproc.analyze(text)
    return analysis.mindmap, analysis.units


def write_mindmap_markdown(text: str, path: Path,
                           clusters: list[textproc.Cluster] | None = None,
                           groups: list[textproc.MindmapGroup] | None = None,
                           units: list[str] | None = None) -> None:
    """Markmap-compatible Markdown mind map.

    ``# root`` > ``## topic`` > ``### sub-topic`` > ``#### sentence``; a topic
    with a single sub-topic lists its sentences directly (``###``).
    """
    groups, sents = _mindmap_groups(text, clusters, groups, units)
    lines = ["# Audio mindmap", ""]
    for group in groups:
        lines.append(f"## {group.label}")
        nested = len(group.clusters) > 1
        for cl in group.clusters:
            if nested:
                lines.append(f"### {textproc.cluster_label(cl, sents)}")
            for i in cl.members:
                lines.append(f"{'####' if nested else '###'} {sents[i][:110]}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mm_text(s: str) -> str:
    s = s.replace('"', "'").replace("\n", " ")
    return s[:110]


def write_mindmap_mermaid(text: str, path: Path,
                          clusters: list[textproc.Cluster] | None = None,
                          groups: list[textproc.MindmapGroup] | None = None,
                          units: list[str] | None = None) -> None:
    """Mermaid flowchart mind map (topic > sub-topic > sentence)."""
    groups, sents = _mindmap_groups(text, clusters, groups, units)
    lines = ["graph TD", '    ROOT["Audio mindmap"]']
    for gi, group in enumerate(groups):
        g = f"G{gi}"
        lines.append(f'    {g}["{_mm_text(group.label)}"]')
        lines.append(f"    ROOT --> {g}")
        nested = len(group.clusters) > 1
        for ci, cl in enumerate(group.clusters):
            parent = g
            if nested:
                parent = f"{g}C{ci}"
                lines.append(f'    {parent}["{_mm_text(textproc.cluster_label(cl, sents))}"]')
                lines.append(f"    {g} --> {parent}")
            for li, member in enumerate(cl.members[:6]):
                lines.append(f'    {parent}L{li}["{_mm_text(sents[member])}"]')
                lines.append(f"    {parent} --> {parent}L{li}")
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


# Characters Obsidian does not allow inside a [[wiki-link]] target.
_WIKILINK_BAD = re.compile(r"[\[\]|#^\\/:*?\"<>]")


def _wikilink(term: str) -> str:
    """Turn a keyword into a safe Obsidian [[wiki-link]] ('' if nothing is left)."""
    name = " ".join(_WIKILINK_BAD.sub(" ", term).split())
    return f"[[{name}]]" if name else ""


def _callout_lines(lines: list[str]) -> list[str]:
    """Prefix lines with '> ' so they stay inside an Obsidian callout."""
    return [f"> {ln}".rstrip() for ln in lines]


def _topic_lines(nodes: list[textproc.TopicNode], depth: int = 0, max_times: int = 3) -> list[str]:
    """Nested Markdown list of [[wiki-links]] (2-space indent per level).

    Each item shows the mention count and, when known, where in the recording
    the topic comes up (first ``max_times`` segment starts, "…" if more).
    """
    lines: list[str] = []
    for node in nodes:
        link = _wikilink(node.term)
        if not link:
            continue
        when = "".join(f" · {_hms(t)}" for t in node.times[:max_times])
        if len(node.times) > max_times:
            when += " …"
        lines.append(f"{'  ' * depth}- {link} ({node.mentions}){when}")
        lines += _topic_lines(node.children, depth + 1)
    return lines


def write_obsidian_note(output_dir: Path, text: str, summary: list[str],
                        keywords: list[tuple[str, int]], max_links: int = 10,
                        max_topics: int = 16, min_char_length: int = 20,
                        tree: list[textproc.TopicNode] | None = None,
                        segments: list[dict] | None = None) -> Path:
    """Write ``obsidian.md``: summary callout, keyword wiki-links, topic tree, transcript.

    ``keywords`` is the ``(term, count)`` list from ``textproc.extract_keywords``
    (bare strings are accepted too); the first ``max_links`` become
    ``[[wiki-links]]``. The topic tree (``textproc.topic_tree``) nests related
    terms as wiki-links with their mention counts, so long multi-topic
    recordings (e.g. a group chat) link into the vault as a tree; up to
    ``max_topics`` top-level topics, ignoring sentences shorter than
    ``min_char_length``. With Whisper ``segments``, every topic also lists the
    timestamps where it comes up. Pass ``tree`` to reuse an existing analysis.
    Returns the path written.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    links: list[str] = []
    for kw in keywords:
        link = _wikilink(kw[0] if isinstance(kw, (tuple, list)) else str(kw))
        if link and link not in links:
            links.append(link)
        if len(links) >= max_links:
            break

    summary_body = [f"{i}. {' '.join(s.split())}" for i, s in enumerate(summary, 1)]
    transcript_body: list[str] = []
    for para in (p.strip() for p in text.splitlines()):
        if para:
            # Blank '>' line between paragraphs keeps them separate in the callout.
            transcript_body += ([""] if transcript_body else []) + [para]

    lines = ["# Audio Brief", "", "> [!summary] Summary"]
    lines += _callout_lines(summary_body or ["_No summary could be extracted._"])
    lines += ["", "## Keywords", "", " · ".join(links) if links else "_No keywords found._", ""]
    if tree is None:
        units = textproc.analysis_units(text, segments)
        tree = textproc.topic_tree(text, max_topics=max_topics, min_char_length=min_char_length,
                                   units=units)
        textproc.attach_timestamps(tree, segments)
    topics = _topic_lines(tree)
    lines += ["## Topics", ""] + (topics or ["_No recurring topics found._"]) + [""]
    lines += ["> [!quote]- Transcript"]
    lines += _callout_lines(transcript_body or ["_Empty transcript._"])

    path = output_dir / "obsidian.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_all(text: str, segments, meta: dict, out_dir: Path,
              summary_n: int = 8, keywords_n: int = 15,
              min_char_length: int = 20, report: dict | None = None) -> list[Path]:
    """Write every artifact from one shared analysis (``textproc.analyze``).

    ``min_char_length`` drops short fragments ("Okay.", "lol") from the
    summary, mind map and topic tree. Pass a dict as ``report`` to receive
    per-stage timings (seconds) and counts. Returns the list of files written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis = textproc.analyze(text, segments, summary_n=summary_n, keywords_n=keywords_n,
                                min_char_length=min_char_length)
    write_start = time.perf_counter()
    summary, keywords = analysis.summary, analysis.keywords
    groups, units = analysis.mindmap, analysis.units

    paths = {
        "transcript.txt": lambda p: write_transcript_txt(segments, p),
        "transcript.srt": lambda p: write_transcript_srt(segments, p),
        "transcript.vtt": lambda p: write_transcript_vtt(segments, p),
        "transcript.json": lambda p: write_transcript_json(segments, meta, p),
        "summary.md": lambda p: write_summary(text, p, summary=summary),
        "keywords.md": lambda p: write_keywords(text, p, keywords=keywords),
        "mindmap.md": lambda p: write_mindmap_markdown(text, p, groups=groups, units=units),
        "mindmap.mmd": lambda p: write_mindmap_mermaid(text, p, groups=groups, units=units),
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
    written.append(write_obsidian_note(out_dir, text, summary, keywords,
                                       min_char_length=min_char_length, tree=analysis.topics))
    if report is not None:
        report.update({
            "timings": {**analysis.timings, "writing files": time.perf_counter() - write_start},
            "words": len(textproc.tokenize(text)),
            "units": len(analysis.units),
            "unit_kind": analysis.unit_kind,
            "topics": len(analysis.topics),
            "mindmap_branches": len(analysis.mindmap),
            "files": len(written),
        })
    return written
