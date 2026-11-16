"""Controlled stress tests on synthetic conversations (benchmarks/datasets.py).

Synthetic data isolates specific failure modes (generic words shared by all
topics, missing punctuation, verbatim repetition) with exact ground truth. The
real-corpus experiments live in tasks.py; these complement, not replace, them.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from audio_brief import textproc, writers

from . import metrics
from .datasets import (
    CONVERSATION_TOPICS,
    GROUP_CHAT_TOPICS,
    SAMPLE_MEETING,
    make_conversation,
    make_group_chat,
)

MEETING_TOPICS = {
    "release & payments": ["release", "mobile", "app", "payment", "integration", "bank", "api",
                           "sandbox", "mock"],
    "customer feedback": ["customer", "feedback", "onboarding", "beta", "search", "results",
                          "redesign"],
    "data pipeline & hiring": ["pipeline", "data", "cloud", "budget", "hourly", "backend",
                               "engineers", "hiring"],
}


@dataclass
class Dataset:
    name: str
    text: str
    segments: list[dict]
    distinctive: dict[str, set[str]]
    kind: str  # "meeting" | "chat" | "conversation"
    size: int  # messages / sentences


def _segments_per_sentence(text: str) -> list[dict]:
    return [{"start": 4.0 * i, "end": 4.0 * (i + 1), "text": s}
            for i, s in enumerate(textproc.sentences(text))]


def datasets(quick: bool) -> list[Dataset]:
    conv_topics = metrics.distinctive_from_nouns(CONVERSATION_TOPICS)
    out = [Dataset("meeting", SAMPLE_MEETING, _segments_per_sentence(SAMPLE_MEETING),
                   metrics.distinctive_from_nouns(MEETING_TOPICS), "meeting",
                   len(textproc.sentences(SAMPLE_MEETING)))]
    chat_n = 200 if quick else 2000
    chat = make_group_chat(chat_n)
    out.append(Dataset(f"verbatim chat {chat_n}", chat, _segments_per_sentence(chat),
                       metrics.distinctive_from_sentences(GROUP_CHAT_TOPICS), "chat", chat_n))
    for n in ((200,) if quick else (200, 2000, 8000)):
        c = make_conversation(n)
        out.append(Dataset(f"conversation {n}", c.text, c.segments, conv_topics, "conversation", n))
    n = 200 if quick else 2000
    c = make_conversation(n, punct=False)
    out.append(Dataset(f"conversation {n}, no punctuation", c.text, c.segments, conv_topics,
                       "conversation", n))
    return out


def _best_time(fn, repeat: int) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def _mindmap_branches(analysis: textproc.Analysis) -> tuple[list[list[str]], list[str]]:
    """Sentences under each top-level mind-map branch (every level, no leaf cap)."""
    units = analysis.units
    full = textproc.build_mindmap("", max_leaves=10**9, units=units, specificity=analysis.specificity)
    groups = textproc.group_mindmap(full, analysis.topics, units)
    return ([[units[i] for c in g.clusters for i in c.members] for g in groups],
            [g.label for g in groups])


def measure(ds: Dataset, repeat: int) -> dict:
    text, segs = ds.text, ds.segments
    a = textproc.analyze(text, segs)
    units, spec = a.units, a.specificity
    row: dict = {"dataset": ds.name, "kind": ds.kind, "size": ds.size,
                 "words": len(textproc.tokenize(text)), "units": len(units)}
    row["t_specificity"] = _best_time(lambda: textproc.term_specificity(units), repeat)
    row["t_summary"] = _best_time(lambda: textproc.summarize(text, units=units), repeat)
    row["t_keywords"] = _best_time(
        lambda: textproc.extract_keywords(text, units=units, specificity=spec), repeat)
    row["t_mindmap"] = _best_time(lambda: textproc.group_mindmap(
        textproc.build_mindmap(text, units=units, specificity=spec), a.topics, units), repeat)
    row["t_topics"] = _best_time(lambda: textproc.attach_timestamps(
        textproc.topic_tree(text, units=units, specificity=spec), segs), repeat)
    with tempfile.TemporaryDirectory() as tmp:
        row["t_export"] = _best_time(
            lambda: writers.write_all(text, segs, {"source": ds.name}, Path(tmp)), repeat)

    for k, v in metrics.topic_tree_quality(a.topics, ds.distinctive).items():
        row[f"tree_{k}"] = v
    row["kw_precision"] = metrics.keyword_precision(a.keywords, ds.distinctive)
    branches, labels = _mindmap_branches(a)
    for k, v in metrics.mindmap_quality(branches, labels, ds.distinctive).items():
        row[f"mm_{k}"] = v
    row["summary_on_topic"] = metrics.summary_on_topic(a.summary, ds.distinctive)
    return row
