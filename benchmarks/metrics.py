"""Quality metrics against corpora with known topics (see benchmarks/datasets.py).

Every metric relies on *distinctive terms*: words used by exactly one topic
(for the templated conversation, the topic nouns). A text unit belongs to the
topic whose distinctive terms it mentions most.
"""

from __future__ import annotations

from collections import Counter

from audio_brief import textproc


def distinctive_from_sentences(topics: dict[str, list[str]]) -> dict[str, set[str]]:
    """Distinctive terms of topics described by example sentences."""
    vocab = {name: set(textproc.content_terms(" ".join(sents))) for name, sents in topics.items()}
    counts = Counter(t for v in vocab.values() for t in v)
    return {name: {t for t in v if counts[t] == 1} for name, v in vocab.items()}


def distinctive_from_nouns(topics: dict[str, list[str]]) -> dict[str, set[str]]:
    return {name: set(nouns) for name, nouns in topics.items()}


def topic_of(text: str, distinctive: dict[str, set[str]]) -> str | None:
    """Majority topic of a text unit by distinctive-term mentions (None if none)."""
    terms = Counter(textproc.content_terms(text))
    scores = {name: sum(terms[t] for t in words) for name, words in distinctive.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.children)


def topic_tree_quality(tree, distinctive: dict[str, set[str]]) -> dict[str, float]:
    """coverage: share of topics with a top-level branch holding >= 2 of their terms.
    purity: share of topical branches whose terms come from a single topic.
    generic_roots: share of top-level branches with no distinctive term at all."""
    # Nodes may be phrases ("bank api"): compare their words.
    subtrees = [{w for n in _walk([root]) for w in n.term.split()} for root in tree]
    covered = {name for name, words in distinctive.items()
               if any(len(terms & words) >= 2 for terms in subtrees)}
    topical = [sum(1 for words in distinctive.values() if terms & words) for terms in subtrees]
    n_topical = sum(1 for k in topical if k)
    return {
        "coverage": len(covered) / len(distinctive),
        "purity": (sum(1 for k in topical if k == 1) / n_topical) if n_topical else 0.0,
        "generic_roots": (sum(1 for k in topical if k == 0) / len(tree)) if tree else 0.0,
        # top-level topical branches per covered topic (1.0 = one branch per topic)
        "fragmentation": (n_topical / len(covered)) if covered else 0.0,
        "roots": len(tree),
        "nodes": sum(1 for _ in _walk(tree)),
    }


def keyword_precision(keywords: list[tuple[str, int]], distinctive: dict[str, set[str]]) -> float:
    """Share of keywords that contain at least one distinctive topic term."""
    if not keywords:
        return 0.0
    all_terms = set().union(*distinctive.values())
    return sum(1 for kw, _ in keywords if set(kw.split()) & all_terms) / len(keywords)


def mindmap_quality(branches: list[list[str]], labels: list[str],
                    distinctive: dict[str, set[str]]) -> dict[str, float]:
    """branches: the sentences under each top-level branch (all levels flattened).
    purity: share of topical sentences that match their branch's majority topic.
    coverage: share of topics that are the majority of at least one branch."""
    agree = total = 0
    majorities = set()
    for sents in branches:
        topics = [t for t in (topic_of(s, distinctive) for s in sents) if t]
        if topics:
            top, n = Counter(topics).most_common(1)[0]
            majorities.add(top)
            agree += n
            total += len(topics)
    return {
        "branches": len(branches),
        "duplicate_labels": len(labels) - len(set(labels)),
        "purity": agree / total if total else 0.0,
        "coverage": len(majorities) / len(distinctive),
    }


def summary_on_topic(summary: list[str], distinctive: dict[str, set[str]]) -> float:
    """Share of summary sentences that mention a topic (not filler or chatter)."""
    if not summary:
        return 0.0
    return sum(1 for s in summary if topic_of(s, distinctive)) / len(summary)
