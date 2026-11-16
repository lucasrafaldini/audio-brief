"""Documentation rule: every Markdown file in the repository carries at least one
Mermaid diagram. Exported files (the notes audio-brief writes for a recording)
are the exception: they are output, not documentation.

This checks presence and the diagram type; whether a diagram renders is checked
with mermaid-cli (see CONTRIBUTING.md), which needs Node and is not run here."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Files written by audio_brief.writers.write_all for each recording, plus agent config files.
EXPORT_NAMES = {"summary.md", "keywords.md", "mindmap.md", "report.md", "obsidian.md", "AGENTS.md", "CLAUDE.md"}
SKIP_DIRS = {"__pycache__", "node_modules"}
SKIP_PATHS = {Path("benchmarks/data")}  # downloaded corpora (not ours; git-ignored)
DIAGRAM_TYPES = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
                 "erDiagram", "gantt", "pie", "mindmap", "timeline", "journey", "quadrantChart", "xychart-beta",
                 "gitGraph", "block-beta", "sankey-beta")
MERMAID = re.compile(r"^```mermaid[ \t]*\n(.*?)^```", re.M | re.S)


def _doc_files() -> list[Path]:
    docs = []
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT)
        dirs = rel.parts[:-1]
        if any(d.startswith(".") or d in SKIP_DIRS or d.startswith("audio-brief-") for d in dirs) \
                or any(skip in rel.parents for skip in SKIP_PATHS):
            continue  # hidden dirs (.git, .venv, .pytest_cache), corpora, default output folders
        if path.name in EXPORT_NAMES:
            continue
        docs.append(path)
    return docs


def test_documentation_files_are_found():
    names = {p.relative_to(ROOT).as_posix() for p in _doc_files()}
    assert {"README.md", "README.pt-BR.md", "README.es.md", "CHANGELOG.md", "CONTRIBUTING.md",
            "tests/data/README.md", "benchmarks/METHODOLOGY.md"} <= names


@pytest.mark.parametrize("path", _doc_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_markdown_file_has_a_mermaid_diagram(path):
    blocks = MERMAID.findall(path.read_text(encoding="utf-8"))
    assert blocks, f"{path.relative_to(ROOT)} has no ```mermaid block"
    for block in blocks:
        first = next((ln.strip() for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("%%")), "")
        assert first.split()[0] in DIAGRAM_TYPES if first else False, \
            f"{path.relative_to(ROOT)}: mermaid block starts with {first!r}, not a diagram type"


def test_translated_readmes_have_as_many_diagrams_as_english():
    count = {name: len(MERMAID.findall((ROOT / name).read_text(encoding="utf-8")))
             for name in ("README.md", "README.pt-BR.md", "README.es.md")}
    assert len(set(count.values())) == 1, count
