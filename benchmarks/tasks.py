"""Benchmark experiments on real corpora. See METHODOLOGY.md for the rationale.

Each experiment returns a dict with its configuration and one record per trial;
``run.py`` turns them into statistics and the report. ``log`` receives
progress lines.
"""

from __future__ import annotations

import math
import platform
import statistics
import tempfile
import time
import tracemalloc
import warnings
from pathlib import Path

from audio_brief import textproc, writers

from . import baselines as bl
from . import metrics, real

OURS = "audio-brief"


def _nmi_ari(gold: list[int], pred: list[int]) -> dict:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    return {"nmi": normalized_mutual_info_score(gold, pred), "ari": adjusted_rand_score(gold, pred)}


def _ours_clusters(comp: real.Composition):
    """audio-brief's top-level mind-map branch for every gold sentence (-1 = not placed)."""
    a = textproc.analyze(comp.text, comp.segments)
    full = textproc.build_mindmap("", max_leaves=10**9, units=a.units, specificity=a.specificity)
    groups = textproc.group_mindmap(full, a.topics, a.units)
    branch_of = {}
    for gi, g in enumerate(groups):
        if any(c.misc for c in g.clusters):
            continue  # the leftovers branch is not a topic
        for c in g.clusters:
            for u in c.members:
                branch_of[u] = gi
    unit_of = real.align(comp, a.units)
    pred = [branch_of.get(u, -1) if u >= 0 else -1 for u in unit_of]
    return a, pred, sum(1 for g in groups if not any(c.misc for c in g.clusters))


def _kw_scores(keywords: list[str], distinctive: dict[str, set[str]]) -> dict:
    """precision: share of keywords containing a reference term of some topic;
    coverage: share of topics with at least one such keyword."""
    words = [set(textproc.content_terms(kw)) for kw in keywords]
    all_terms = set().union(*distinctive.values()) if distinctive else set()
    precise = [bool(w & all_terms) for w in words]
    covered = {name for name, terms in distinctive.items() if any(w & terms for w in words)}
    return {"precision": sum(precise) / len(keywords) if keywords else 0.0,
            "coverage": len(covered) / len(distinctive) if distinctive else 0.0}


def topic_discovery(source: str, settings: list[int], trials: int, log, split: str = "test") -> dict:
    """Clustering, topic tree and keyword quality on multi-topic transcripts of real text.

    ``split`` picks the half of the corpus (``real.split_of``): parameters are
    chosen on "dev", results are reported on "test".
    """
    if source == "wikipedia":
        pool = [a for a in real.wikipedia(split) if len(a["sentences"]) >= 60]
        per_topic = 40
    else:
        pool = [p for p in real.newsgroups(split) if len(p["text"].split()) >= 20]
    runs = []
    for k in settings:
        t0 = time.perf_counter()
        for trial in range(trials):
            seed = 1000 * k + trial
            comp = (real.compose_articles(pool, k, per_topic, seed) if source == "wikipedia"
                    else real.compose_posts(pool, 40, seed))
            gold = comp.labels
            ref = real.distinctive_terms(comp, textproc.content_terms)
            a, pred, branches = _ours_clusters(comp)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                clustering = {
                    OURS: _nmi_ari(gold, pred),
                    "TF-IDF + k-means (true k)": _nmi_ari(gold, bl.clusters_tfidf_kmeans(comp.sentences, len(comp.topics), seed)),
                    "LDA (true k)": _nmi_ari(gold, bl.clusters_lda(comp.sentences, len(comp.topics), seed)),
                    "random clusters (true k)": _nmi_ari(gold, bl.clusters_random(comp.sentences, len(comp.topics), seed)),
                    "one cluster": _nmi_ari(gold, bl.clusters_single(comp.sentences)),
                }
            tree = metrics.topic_tree_quality(a.topics, ref)
            kw = {
                OURS: _kw_scores([k_ for k_, _ in a.keywords], ref),
                "frequency": _kw_scores(bl.keywords_frequency(comp.text, 15), ref),
                "YAKE": _kw_scores(bl.keywords_yake(comp.text, 15), ref),
            }
            runs.append({"k": len(comp.topics), "trial": trial, "seed": seed, "sentences": len(comp.sentences),
                         "words": len(comp.text.split()), "topics": comp.topics,
                         "placed": sum(1 for p in pred if p >= 0) / len(pred), "branches": branches,
                         "clustering": clustering, "tree": tree, "keywords": kw})
        log(f"{source} k={k}: {trials} trials in {time.perf_counter() - t0:.1f}s")
    return {"source": source, "settings": settings, "trials": trials, "runs": runs}


def summaries(max_articles: int | None, log, split: str = "test") -> dict:
    """ROUGE of each system's summary of the article body against the article's lead."""
    from nltk.stem.porter import PorterStemmer  # noqa: F401 (rouge-score's stemmer; fail early if missing)
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    arts = [a for a in real.wikipedia(split)
            if len(a["lead"].split()) >= 40 and len(a["body"].split()) >= 400]
    arts = arts[:max_articles] if max_articles else arts
    runs, t0 = [], time.perf_counter()
    for i, art in enumerate(arts):
        body = " ".join(art["body"].split()[:3000])  # same capped input for every system
        sents = real.split_sentences(body)
        budget = min(len(art["lead"].split()), 150)
        avg = statistics.fmean(len(s.split()) for s in sents)
        n = max(1, math.ceil(budget / avg) + 1)

        def cut(selected: list[str]) -> str:
            return " ".join(" ".join(selected).split()[:budget])

        outputs = {
            OURS: textproc.summarize(body, ratio=1.0, max_sentences=n, units=sents),
            "Lead-k": bl.summary_lead(sents, n),
            "random sentences": bl.summary_random(sents, n, seed=i),
            "TextRank": bl.summary_textrank(body, budget),
            "LexRank": bl.summary_lexrank(body, n),
        }
        scores = {}
        for system, sel in outputs.items():
            r = scorer.score(art["lead"], cut(sel))
            scores[system] = {m: r[m].fmeasure for m in ("rouge1", "rouge2", "rougeL")}
        runs.append({"title": art["title"], "budget_words": budget, "body_words": len(body.split()),
                     "scores": scores})
        if (i + 1) % 20 == 0:
            log(f"summaries: {i + 1}/{len(arts)} articles")
    log(f"summaries: {len(arts)} articles in {time.perf_counter() - t0:.1f}s")
    return {"articles": len(arts), "runs": runs}


def title_keywords(max_articles: int | None, log, split: str = "test") -> dict:
    """Does each system rank the article's subject (its title words) among the top 10 keywords?"""
    from nltk.stem.porter import PorterStemmer

    stem = PorterStemmer().stem

    def stems(text: str) -> list[str]:
        return [stem(w) for w in textproc.content_terms(text)]

    arts = []
    for a in real.wikipedia(split):
        title = a["title"].split(" (")[0]
        tw = set(stems(title))
        body_stems = stems(" ".join(a["body"].split()[:2000]))
        if (a["title"].startswith("List of") or not tw or len(a["body"].split()) < 400
                or any(body_stems.count(w) < 2 for w in tw)):
            continue
        arts.append((a, tw))
    arts = arts[:max_articles] if max_articles else arts
    runs, t0 = [], time.perf_counter()
    for a, tw in arts:
        body = " ".join(a["body"].split()[:2000])
        outputs = {
            OURS: [k for k, _ in textproc.extract_keywords(body, n=10)],
            "frequency": bl.keywords_frequency(body, 10),
            "YAKE": bl.keywords_yake(body, 10),
            "TextRank": bl.keywords_textrank(body, 10),
        }
        scores = {}
        for system, kws in outputs.items():
            kw_stems = [set(stems(k)) for k in kws]
            found = set().union(*kw_stems) if kw_stems else set()
            first = next((r + 1 for r, s in enumerate(kw_stems) if s & tw), None)
            scores[system] = {"title_recall": len(tw & found) / len(tw), "hit": float(bool(tw & found)),
                              "mrr": 1.0 / first if first else 0.0}
        runs.append({"title": a["title"], "scores": scores})
    log(f"title keywords: {len(arts)} articles in {time.perf_counter() - t0:.1f}s")
    return {"articles": len(arts), "runs": runs}


# --- performance -------------------------------------------------------------------------

def environment() -> dict:
    cpu = platform.processor() or platform.machine()
    try:
        for line in open("/proc/cpuinfo", encoding="utf-8"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    mem = None
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemTotal"):
                mem = f"{int(line.split()[1]) / 1024 / 1024:.0f} GB"
    except OSError:
        pass
    import os
    import subprocess

    repo = Path(__file__).resolve().parent.parent  # the project root (contains audio_brief/)
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                check=True, cwd=repo).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "audio_brief"], capture_output=True,
                                    text=True, cwd=repo).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unknown", False
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "os": f"{platform.system()} {platform.release()}", "cpu": cpu, "cores": os.cpu_count(),
            "memory": mem, "git_commit": commit, "uncommitted_changes_in_audio_brief": dirty}


def performance(sizes: list[int], repeats: dict[int, int], per_address: int | None, log) -> dict:
    speeches = real.sotu()
    words = " ".join(s["text"] for s in speeches).split()
    scaling = []
    for n in sizes:
        text = " ".join(words[:n])
        reps = repeats.get(n, 1)
        if n <= 100_000:
            textproc.analyze(text)  # warm-up (imports, caches)
        textproc._content_terms.cache_clear()
        totals, exports, stages = [], [], []
        for _ in range(reps):
            textproc._content_terms.cache_clear()  # measure cold, like a new recording
            t0 = time.perf_counter()
            a = textproc.analyze(text)
            totals.append(time.perf_counter() - t0)
            stages.append(a.timings)
            with tempfile.TemporaryDirectory() as tmp:
                textproc._content_terms.cache_clear()
                t0 = time.perf_counter()
                writers.write_all(text, [], {"source": "sotu"}, Path(tmp))
                exports.append(time.perf_counter() - t0)
        peak = None
        if n <= 300_000:
            textproc._content_terms.cache_clear()
            tracemalloc.start()
            textproc.analyze(text)
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        stage_median = {st: statistics.median(s[st] for s in stages) for st in stages[0]}
        scaling.append({"words": n, "units": len(a.units), "repeats": reps, "analyze_s": totals,
                        "export_s": exports, "stages_median_s": stage_median, "peak_bytes": peak})
        log(f"performance: {n:,} words, {reps} run(s): analyze median {statistics.median(totals):.2f}s, "
            f"export median {statistics.median(exports):.2f}s"
            + (f", peak memory {peak / 1e6:.0f} MB" if peak else ""))
    per = []
    if per_address:
        step = max(1, len(speeches) // per_address)
        for s in speeches[::step][:per_address]:
            textproc._content_terms.cache_clear()
            t0 = time.perf_counter()
            textproc.analyze(s["text"])
            per.append({"year": s["year"], "words": len(s["text"].split()), "analyze_s": time.perf_counter() - t0})
        log(f"performance: {len(per)} individual addresses analysed")
    return {"corpus": "State of the Union addresses, chronological", "scaling": scaling, "per_address": per}
