"""Real-corpus loaders and the multi-topic transcript compositions.

Data comes from ``benchmarks/fetch_data.py`` (pinned + checksummed). Sentence
splitting for the *gold* side uses a neutral rule (end punctuation followed by
a capital letter), independent of ``audio_brief.textproc``, so the reference
is not shaped by the system under test.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).with_name("data")
_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z\"'(\[])")


def split_sentences(text: str, min_words: int = 5) -> list[str]:
    out = []
    for para in text.split("\n"):
        for s in _SPLIT.split(para.strip()):
            s = " ".join(s.split())
            if len(s.split()) >= min_words:
                out.append(s)
    return out


def split_of(key: str) -> str:
    """Deterministic half of the data: "dev" (used to choose parameters) or
    "test" (used only to report results). SHA-1 parity of the title / post."""
    return "dev" if int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16) % 2 else "test"


def _jsonl(name: str) -> list[dict]:
    path = DATA / f"{name}.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} is missing: run `make bench-data` first.")
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def wikipedia(split: str | None = None) -> list[dict]:
    """Articles with their lead, body text and body sentences (optionally one split)."""
    arts = []
    for a in _jsonl("wikipedia"):
        if split and split_of(a["title"]) != split:
            continue
        body = "\n".join(s["text"] for s in a["sections"])
        arts.append({"title": a["title"], "lead": a["lead"], "body": body, "sentences": split_sentences(body)})
    return arts


def newsgroups(split: str | None = None) -> list[dict]:
    return [{"group": p["group"], "text": p["text"], "sentences": split_sentences(p["text"], min_words=3)}
            for p in _jsonl("newsgroups") if not split or split_of(p["text"]) == split]


def sotu() -> list[dict]:
    return _jsonl("sotu")


@dataclass
class Composition:
    """A synthetic transcript made of real sentences with a known topic each."""
    sentences: list[str]
    labels: list[int]
    topics: list[str]  # label -> source name (article title / newsgroup)
    text: str
    spans: list[tuple[int, int]]  # character span of each sentence in ``text``
    segments: list[dict]  # one Whisper-like segment per sentence (4 s each)


def _finish(sentences: list[str], labels: list[int], topics: list[str]) -> Composition:
    spans, pos = [], 0
    for s in sentences:
        spans.append((pos, pos + len(s)))
        pos += len(s) + 1
    segments = [{"start": 4.0 * i, "end": 4.0 * (i + 1), "text": s} for i, s in enumerate(sentences)]
    return Composition(sentences, labels, topics, " ".join(sentences), spans, segments)


def compose_articles(articles: list[dict], k: int, per_topic: int, seed: int,
                     block: tuple[int, int] = (2, 8)) -> Composition:
    """k random articles; a window of ``per_topic`` consecutive sentences from each,
    interleaved in blocks of 2-8 sentences of a randomly chosen article, so
    topics come back several times like in a conversation (Choi-style
    composition, Choi 2000, with topic recurrence)."""
    rnd = random.Random(seed)
    chosen = rnd.sample(articles, k)
    queues = []
    for art in chosen:
        start = rnd.randrange(0, len(art["sentences"]) - per_topic + 1)
        queues.append(list(art["sentences"][start:start + per_topic]))
    sentences, labels = [], []
    while any(queues):
        live = [i for i, q in enumerate(queues) if q]
        i = rnd.choice(live)
        for _ in range(rnd.randint(*block)):
            if queues[i]:
                sentences.append(queues[i].pop(0))
                labels.append(i)
    return _finish(sentences, labels, [a["title"] for a in chosen])


def compose_posts(posts: list[dict], n_posts: int, seed: int, block: tuple[int, int] = (1, 3)) -> Composition:
    """A thread-like transcript of real Usenet posts from both newsgroups, in
    blocks of 1-3 consecutive posts of the same group."""
    rnd = random.Random(seed)
    groups = sorted({p["group"] for p in posts})
    pools = {g: rnd.sample([p for p in posts if p["group"] == g], n_posts // len(groups)) for g in groups}
    sentences, labels = [], []
    while any(pools.values()):
        g = rnd.choice([g for g in groups if pools[g]])
        for _ in range(rnd.randint(*block)):
            if pools[g]:
                post = pools[g].pop()
                sentences += post["sentences"]
                labels += [groups.index(g)] * len(post["sentences"])
    return _finish(sentences, labels, groups)


def align(comp: Composition, units: list[str]) -> list[int]:
    """For every gold sentence, the index of the system unit covering its first
    character (-1 if none). Units are located in the text in order."""
    unit_start, cursor = [], 0
    for u in units:
        probe = u[:40]
        at = comp.text.find(probe, cursor)
        if at < 0:  # units are whitespace-normalised; fall back to a looser search
            at = comp.text.find(probe.split()[0], cursor) if probe.split() else -1
        unit_start.append(at if at >= 0 else cursor)
        cursor = max(cursor, unit_start[-1] + 1)
    out, j = [], 0
    for start, _ in comp.spans:
        while j + 1 < len(unit_start) and unit_start[j + 1] <= start:
            j += 1
        out.append(j if unit_start and unit_start[j] <= start else -1)
    return out


def distinctive_terms(comp: Composition, content_terms, min_mentions: int = 3,
                      share: float = 0.8) -> dict[str, set[str]]:
    """Terms mentioned in >= min_mentions gold sentences, >= share of them in
    one topic: the reference vocabulary of each topic (from the labels only)."""
    from collections import Counter, defaultdict

    seen: dict[str, Counter] = defaultdict(Counter)
    for sent, lab in zip(comp.sentences, comp.labels):
        for t in set(content_terms(sent)):
            seen[t][lab] += 1
    out: dict[str, set[str]] = {name: set() for name in comp.topics}
    for term, by_topic in seen.items():
        total = sum(by_topic.values())
        lab, n = by_topic.most_common(1)[0]
        if total >= min_mentions and n / total >= share:
            out[comp.topics[lab]].add(term)
    return out
