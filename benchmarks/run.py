"""Run the benchmarks and write benchmarks/RESULTS.md + benchmarks/results.json.

    python -m benchmarks.run                  # full run (~15 min)
    python -m benchmarks.run --quick          # small run of every experiment (~1-2 min)
    python -m benchmarks.run --only topics,summaries
    python -m benchmarks.run --render-only    # rebuild RESULTS.md from results.json

Needs the data from ``python -m benchmarks.fetch_data`` and the ``[bench]``
extras (``make bench`` does both). Methodology: benchmarks/METHODOLOGY.md.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import statistics
import sys
import time
from pathlib import Path

from . import asr_bench, parallel_bench, stats, synthetic, tasks

HERE = Path(__file__).parent
EXPERIMENTS = ("topics", "keywords", "summaries", "performance", "asr", "parallel", "synthetic")
OURS = tasks.OURS


def log(msg: str) -> None:
    print(f"    [{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def config(quick: bool) -> dict:
    if quick:
        return {"wiki_k": [3], "trials": 3, "news_trials": 3, "max_articles": 10,
                "sizes": [10_000, 30_000], "repeats": {10_000: 2, 30_000: 1}, "per_address": 5,
                "asr_long_minutes": 1, "parallel_long_minutes": 1}
    return {"wiki_k": [3, 5, 8], "trials": 20, "news_trials": 20, "max_articles": None,
            "sizes": [10_000, 30_000, 100_000, 300_000, 1_000_000],
            "repeats": {10_000: 5, 30_000: 5, 100_000: 3, 300_000: 2, 1_000_000: 1}, "per_address": 40,
            "asr_long_minutes": 5, "parallel_long_minutes": 4}


def collect(quick: bool, only: set[str]) -> dict:
    cfg = config(quick)
    manifest_path = HERE / "data" / "manifest.json"
    needs_data = bool(only & {"topics", "keywords", "summaries", "performance", "asr", "parallel"})
    if needs_data and not manifest_path.exists():
        raise SystemExit("benchmarks/data is missing: run `make bench-data` (or python -m benchmarks.fetch_data).")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"sources": {}, "datasets": {}}
    out = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "quick": quick, "config": cfg,
           "environment": tasks.environment(), "data": manifest, "experiments": {}}
    plan = [name for name in EXPERIMENTS if name in only]
    for i, name in enumerate(plan, 1):
        print(f"==> [{i}/{len(plan)}] {name}", flush=True)
        t0 = time.perf_counter()
        if name == "topics":
            out["experiments"]["topics_wikipedia"] = tasks.topic_discovery("wikipedia", cfg["wiki_k"], cfg["trials"], log)
            out["experiments"]["topics_newsgroups"] = tasks.topic_discovery("newsgroups", [2], cfg["news_trials"], log)
        elif name == "keywords":
            out["experiments"]["title_keywords"] = tasks.title_keywords(cfg["max_articles"], log)
        elif name == "summaries":
            out["experiments"]["summaries"] = tasks.summaries(cfg["max_articles"], log)
        elif name == "parallel":
            out["experiments"]["parallel"] = parallel_bench.benchmark(log, cfg["parallel_long_minutes"], quick)
        elif name == "asr":
            out["experiments"]["asr"] = asr_bench.benchmark(log, cfg["asr_long_minutes"])
        elif name == "performance":
            out["experiments"]["performance"] = tasks.performance(cfg["sizes"], cfg["repeats"], cfg["per_address"], log)
        elif name == "synthetic":
            rows = []
            for ds in synthetic.datasets(quick):
                rows.append(synthetic.measure(ds, 1))
                log(f"synthetic: {ds.name}")
            out["experiments"]["synthetic"] = {"rows": rows}
        print(f"    done in {time.perf_counter() - t0:.1f}s", flush=True)
    return out


# --- rendering ------------------------------------------------------------------------------

def _f(x: float, pct: bool = False) -> str:
    return f"{100 * x:.0f}%" if pct else f"{x:.3f}"


def _ci(values: list[float], pct: bool = False) -> str:
    c = stats.ci(values)
    return f"{_f(c['mean'], pct)} [{_f(c['lo'], pct)}, {_f(c['hi'], pct)}]"


def _vs(ours: list[float], other: list[float], pct: bool = False) -> str:
    p = stats.paired(ours, other)
    sign = "+" if p["diff"] >= 0 else "−"
    d = abs(p["diff"])
    return (f"{sign}{_f(d, pct)} [{_f(p['lo'], pct)}, {_f(p['hi'], pct)}] · "
            f"{p['wins']}/{p['ties']}/{p['losses']} · **{p['verdict']}**")


def _chart(title: str, labels: list[str], values: list[float], y_label: str, y_max: float) -> list[str]:
    xs = ", ".join(f'"{label}"' for label in labels)
    vals = ", ".join(f"{v:.3f}" if y_max <= 1 else f"{v:.1f}" for v in values)
    return ["```mermaid", "xychart-beta", f'    title "{title}"', f"    x-axis [{xs}]",
            f'    y-axis "{y_label}" 0 --> {y_max:g}', f"    bar [{vals}]", "```", ""]


def _systems(runs: list[dict], key: str) -> list[str]:
    names = list(runs[0][key].keys())
    return [OURS] + [n for n in names if n != OURS]


def render_topics(exp: dict, title: str, what: str) -> list[str]:
    runs = exp["runs"]
    lines = [f"### {title}", "", what, ""]
    for k in sorted({r["k"] for r in runs}):
        rk = [r for r in runs if r["k"] == k]
        words = statistics.median(r["words"] for r in rk)
        lines += [f"**{k} topics** · {len(rk)} trials · median {words:,.0f} words per transcript", "",
                  "| System | NMI, mean [95% CI] | ARI, mean [95% CI] | audio-brief vs system, NMI diff [95% CI] · wins/ties/losses |",
                  "|---|---|---|---|"]
        ours = [r["clustering"][OURS]["nmi"] for r in rk]
        for system in _systems(rk, "clustering"):
            nmi = [r["clustering"][system]["nmi"] for r in rk]
            ari = [r["clustering"][system]["ari"] for r in rk]
            versus = "—" if system == OURS else _vs(ours, nmi)
            lines.append(f"| {system} | {_ci(nmi)} | {_ci(ari)} | {versus} |")
        lines.append("")
    # chart for the middle setting
    ks = sorted({r["k"] for r in runs})
    k = ks[len(ks) // 2]
    rk = [r for r in runs if r["k"] == k]
    systems = _systems(rk, "clustering")
    means = [statistics.fmean(r["clustering"][s]["nmi"] for r in rk) for s in systems]
    short = [s.replace(" (true k)", "*").replace("TF-IDF + k-means", "k-means") for s in systems]
    lines += _chart(f"NMI with {k} topics (* = given the true number of topics)", short, means, "NMI", 1)
    return lines


def render_tree(exps: list[tuple[str, dict]]) -> list[str]:
    lines = ["| Transcripts | Topics found (coverage) | Purity | Generic top-level topics | Top-level topics per real topic | "
             "Sentences placed in a topic branch | Mind-map branches |", "|---|---|---|---|---|---|---|"]
    for name, exp in exps:
        for k in sorted({r["k"] for r in exp["runs"]}):
            rk = [r for r in exp["runs"] if r["k"] == k]
            lines.append(
                f"| {name}, {k} topics | {_ci([r['tree']['coverage'] for r in rk], True)} | "
                f"{_ci([r['tree']['purity'] for r in rk], True)} | {_ci([r['tree']['generic_roots'] for r in rk], True)} | "
                f"{_ci([r['tree']['fragmentation'] for r in rk])} | {_ci([r['placed'] for r in rk], True)} | "
                f"{statistics.median(r['branches'] for r in rk):.0f} (median) |")
    return lines + [""]


def render_topic_keywords(exps: list[tuple[str, dict]]) -> list[str]:
    lines = ["| Transcripts | System | Topical precision@15 | Topics covered@15 | audio-brief vs system, precision diff · w/t/l |",
             "|---|---|---|---|---|"]
    for name, exp in exps:
        for k in sorted({r["k"] for r in exp["runs"]}):
            rk = [r for r in exp["runs"] if r["k"] == k]
            ours = [r["keywords"][OURS]["precision"] for r in rk]
            for system in _systems(rk, "keywords"):
                prec = [r["keywords"][system]["precision"] for r in rk]
                cov = [r["keywords"][system]["coverage"] for r in rk]
                versus = "—" if system == OURS else _vs(ours, prec, True)
                lines.append(f"| {name}, {k} topics | {system} | {_ci(prec, True)} | {_ci(cov, True)} | {versus} |")
    return lines + [""]


def render_scores(exp: dict, metrics_: list[tuple[str, str]], primary: str, pct: bool) -> list[str]:
    runs = exp["runs"]
    systems = _systems(runs, "scores")
    head = "| System | " + " | ".join(f"{label}, mean [95% CI]" for _, label in metrics_) + \
           f" | audio-brief vs system ({dict(metrics_)[primary]}) · w/t/l |"
    lines = [head, "|---|" + "---|" * (len(metrics_) + 1)]
    ours = [r["scores"][OURS][primary] for r in runs]
    for system in systems:
        cells = [_ci([r["scores"][system][m] for r in runs], pct) for m, _ in metrics_]
        versus = "—" if system == OURS else _vs(ours, [r["scores"][system][primary] for r in runs], pct)
        lines.append(f"| {system} | " + " | ".join(cells) + f" | {versus} |")
    means = [statistics.fmean(r["scores"][s][primary] for r in runs) for s in systems]
    return lines + [""] + _chart(dict(metrics_)[primary], systems, means, dict(metrics_)[primary], 1)


def render_performance(exp: dict) -> list[str]:
    sc = exp["scaling"]
    lines = ["| Words | Units | Runs | analyze(), median [IQR] | Full export, median | Throughput | Peak memory (analyze) |",
             "|---:|---:|---:|---|---:|---:|---:|"]
    for row in sc:
        q = stats.quantiles(row["analyze_s"])
        exp_med = statistics.median(row["export_s"])
        peak = f"{row['peak_bytes'] / 1e6:.0f} MB" if row["peak_bytes"] else "not measured"
        lines.append(f"| {row['words']:,} | {row['units']:,} | {row['repeats']} | {q['median']:.2f}s "
                     f"[{q['p25']:.2f}, {q['p75']:.2f}] | {exp_med:.2f}s | "
                     f"{row['words'] / q['median']:,.0f} words/s | {peak} |")
    fit = stats.loglog_fit([r["words"] for r in sc], [statistics.median(r["analyze_s"]) for r in sc]) if len(sc) > 1 else None
    lines.append("")
    if fit:
        lines += [f"Fitted scaling: analysis time ∝ words^{fit['exponent']:.2f} (R² = {fit['r2']:.3f}; "
                  "1.00 would be perfectly linear).", ""]
        per_k = [1000 * statistics.median(r["analyze_s"]) / (r["words"] / 1000) for r in sc]
        labels = [f"{r['words'] // 1000}k" for r in sc]
        lines += _chart("analyze(): milliseconds per 1,000 words", labels, per_k, "ms per 1,000 words",
                        round(max(per_k) * 1.3 + 1))
    ref = max((r for r in sc if r["words"] <= 100_000), key=lambda r: r["words"])
    stages = ref["stages_median_s"]
    total = sum(stages.values())
    lines += [f"Where the time goes at {ref['words']:,} words (median of {ref['repeats']} runs):", "",
              "| Stage | Time | Share |", "|---|---:|---:|"]
    lines += [f"| {st} | {sec * 1000:.0f} ms | {100 * sec / total:.0f}% |" for st, sec in stages.items()]
    lines.append("")
    lines += _chart(f"analyze() stages at {ref['words'] // 1000}k words (ms)", list(stages),
                    [s * 1000 for s in stages.values()], "ms", round(max(stages.values()) * 1300 + 1))
    per = exp.get("per_address") or []
    if per:
        w = [p["words"] for p in per]
        t = [p["analyze_s"] for p in per]
        lines += [f"Single recordings: {len(per)} individual State of the Union addresses "
                  f"({min(w):,}-{max(w):,} words, median {statistics.median(w):,.0f}): analysis took a median of "
                  f"{statistics.median(t) * 1000:.0f} ms (slowest {max(t) * 1000:.0f} ms).", ""]
    return lines


def render_asr(exp: dict) -> list[str]:
    def wer(d: dict) -> str:
        return f"{100 * d['wer']:.0f}% [{100 * d['lo']:.0f}, {100 * d['hi']:.0f}]" if "lo" in d else f"{100 * d['wer']:.0f}%"

    lines = [f"> **Small test set**: {exp['reference_words']} transcribed words ({exp['items']} files, "
             f"{exp['audio_s'] / 60:.1f} min of real speech in total). Word error rates have wide intervals; "
             "treat them as indicative.", "",
             "| Engine | Status | WER, all [95% CI] | read speech | conversation, per turn | conversation, whole file | "
             "Speed (real-time factor) | Long file | Peak memory |", "|---|---|---|---|---|---|---|---|---|"]
    for e in exp["engines"]:
        if not e["available"]:
            lines.append(f"| {e['engine']} | **not measured**: {e['reason']} | | | | | | | |")
            continue
        lg = e["long"]
        lines.append(f"| {e['engine']} | {e['detail']} | {wer(e['wer_all'])} | {wer(e['wer_read'])} | "
                     f"{wer(e['wer_conversation_turns'])} | {wer(e['wer_conversation_whole'])} | "
                     f"{e['rtf_median']:.2f} (median of {e['rtf_files']} files) | {lg['audio_s'] / 60:.0f} min in "
                     f"{lg['decode_s']:.0f} s (RTF {lg['rtf']:.2f}) | {lg['peak_rss_bytes'] / 1e6:.0f} MB |")
    fp = exp["footprint"]
    lines += ["", "Real-time factor = processing time / audio length (below 1 is faster than real time), one CPU "
              "process. Peak memory is the engine process's maximum resident size, model included.", "",
              f"Installed size: PocketSphinx {fp['pocketsphinx'] / 1e6:.0f} MB; Whisper with PyTorch "
              f"{fp['whisper'] / 1e9:.1f} GB" + (f" plus {fp['whisper_weights_cached'] / 1e6:.0f} MB of cached "
              "model weights" if fp["whisper_weights_cached"] else "") + " (as installed here).", ""]
    for e in exp["engines"]:
        if e["available"]:
            lines += [f"Examples ({e['engine']}), after normalisation:", ""]
            for item, ex in e["examples"].items():
                lines += [f"- *{item}*", f"  - reference: {asr_bench.normalize(ex['reference'])}",
                          f"  - recognised: {asr_bench.normalize(ex['hypothesis'])}"]
            lines.append("")
    return lines


def render_parallel(exp: dict) -> list[str]:
    if not exp.get("available"):
        return [f"Not measured: {exp.get('reason')}.", ""]
    b, lg = exp["batch"], exp["long"]
    return [
        f"Machine: {exp['cpus']} CPU cores, {exp['memory_gb']:.1f} GB available. Engine: PocketSphinx (Whisper "
        "not measured, see section 6). Both runs of each row use the same worker-process machinery; only the "
        "plan differs.", "",
        "| Work | One worker | Automatic plan | Speed-up | Word error rate |", "|---|---:|---:|---:|---|",
        f"| Batch: {b['files']} real recordings, {b['audio_s'] / 60:.1f} min of audio | {b['sequential_s']:.0f} s | "
        f"{b['parallel_s']:.0f} s ({b['workers']} workers, {b['units']} units) | **{b['speedup']:.1f}x** | "
        + ("same decoding (no file was split) |" if b["units"] == b["files"] else
           f"{b['units'] - b['files']} extra unit(s): long files were split; see the next row for what splitting "
           "does to accuracy |"),
        f"| One long recording ({lg['audio_s'] / 60:.1f} min, fully transcribed) | {lg['whole_s']:.0f} s (whole) | "
        f"{lg['split_s']:.0f} s ({lg['parts']} parts on {lg['workers']} workers) | **{lg['speedup']:.1f}x** | "
        f"whole {100 * lg['wer_whole']:.1f}% vs split {100 * lg['wer_split']:.1f}% "
        f"({lg['reference_words']} reference words) |", "",
        f"Splitting changes which words PocketSphinx outputs ({100 * lg['transcripts_differ']:.0f}% of words differ "
        "between the whole and the split transcript: its decoding adapts over a recording), but it does not "
        "make the transcript worse against the reference. The long recording is a single file, so treat the "
        "WER comparison as indicative.", "",
        "```mermaid", "xychart-beta", '    title "Wall time in seconds (lower is better)"',
        '    x-axis ["batch, 1 worker", "batch, auto plan", "long file, whole", "long file, split"]',
        f'    y-axis "seconds" 0 --> {math.ceil(max(b["sequential_s"], lg["whole_s"]) / 10) * 10}',
        f'    bar [{b["sequential_s"]:.0f}, {b["parallel_s"]:.0f}, {lg["whole_s"]:.0f}, {lg["split_s"]:.0f}]',
        "```", ""]


def render_synthetic(rows: list[dict]) -> list[str]:
    lines = ["| Dataset | Words | Topic tree coverage | Purity | Generic top-level | Branches per topic | "
             "Keyword precision | Mind-map purity | Full export |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['dataset']} | {r['words']:,} | {_f(r['tree_coverage'], True)} | {_f(r['tree_purity'], True)} | "
                     f"{_f(r['tree_generic_roots'], True)} | {r['tree_fragmentation']:.1f} | {_f(r['kw_precision'], True)} | "
                     f"{_f(r['mm_purity'], True)} | {r['t_export'] * 1000:.0f} ms |")
    return lines + [""]


def render(res: dict) -> str:
    env, data, ex = res["environment"], res["data"], res["experiments"]
    lines = [
        "# Benchmark results",
        "",
        f"Generated {res['generated']} by `make bench{'-quick' if res['quick'] else ''}` "
        "(`python -m benchmarks.run`). **Do not edit by hand**; raw numbers for every trial are in "
        "[`results.json`](results.json). How and why each number is measured: "
        "[METHODOLOGY.md](METHODOLOGY.md).",
        "",
    ]
    def machine(e: dict) -> tuple:
        return tuple(e.get(k) for k in ("os", "cpu", "cores", "memory", "python"))

    later = sorted((exp["measured_at"], name, machine(exp.get("environment", env)) == machine(env))
                   for name, exp in ex.items() if isinstance(exp, dict) and exp.get("measured_at"))
    if later:
        lines += ["Re-measured later with `--only`: " + "; ".join(
            f"{name} on {when}" + ("" if same else " **on a different machine** (see results.json)")
            for when, name, same in later) + ".", ""]
    if res["quick"]:
        lines += ["> **Quick run**: few trials and small sizes; confidence intervals are wide. "
                  "Use `make bench` for reportable numbers.", ""]
    lines += ["## Environment", "", "| | |", "|---|---|"]
    lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in env.items()]
    lines += ["", "## Data", "", "| Dataset | Records | Words | SHA-256 (prefix) | Licence |", "|---|---:|---:|---|---|"]
    if not data["datasets"]:
        lines.append("| (real corpora not used in this run) | | | | |")
    for name, d in data["datasets"].items():
        lines.append(f"| {name} | {d['records']} | {d['words']:,} | `{d['sha256'][:12]}` | {d['licence']} |")
    lines += ["", "Sources: " + "; ".join(f"{s['what']} ({s['url'].split('/')[2]})" for s in data["sources"].values())
              + ". Checksums are verified before use (`benchmarks/fetch_data.py`).", ""]
    lines += ["How to read the tables: values are means over trials with a 95% bootstrap confidence interval "
              "in brackets. *audio-brief vs system* is the paired difference on the same trials, its 95% CI, "
              "how many trials audio-brief won/tied/lost, and a verdict that says **better** or **worse** only "
              "when the interval excludes zero.", ""]

    if "topics_wikipedia" in ex:
        lines += ["## 1. Topic discovery in multi-topic transcripts", "",
                  "Does audio-brief put sentences about the same subject in the same mind-map branch? "
                  "Scored with NMI and ARI (0 = chance, 1 = perfect) against the true source of every sentence; "
                  "sentences audio-brief leaves out (fragments, leftovers) count as one extra cluster.", ""]
        lines += render_topics(ex["topics_wikipedia"], "Wikipedia mixtures",
                               "Real encyclopedia sentences from k random articles, 40 consecutive sentences each, "
                               "interleaved in blocks of 2-8 so every subject comes back several times.")
        lines += render_topics(ex["topics_newsgroups"], "Usenet threads",
                               "Real posts from alt.atheism and sci.space (20 Newsgroups), 40 per transcript, in "
                               "blocks of 1-3 posts: informal, conversational text.")
        lines += ["## 2. Topic tree quality", "",
                  "Measured on the same transcripts. Reference topic words are those mentioned in ≥ 3 sentences, "
                  "≥ 80% of them from one source.", ""]
        lines += render_tree([("Wikipedia", ex["topics_wikipedia"]), ("Usenet", ex["topics_newsgroups"])])
        lines += ["## 3. Keywords", "", "### Topical precision in multi-topic transcripts", "",
                  "Share of the top 15 keywords that are reference topic words, and share of topics that get at "
                  "least one.", ""]
        lines += render_topic_keywords([("Wikipedia", ex["topics_wikipedia"]), ("Usenet", ex["topics_newsgroups"])])
    if "title_keywords" in ex:
        e = ex["title_keywords"]
        lines += ["### Article subject in the top 10 keywords", "",
                  f"{e['articles']} Wikipedia articles (first 2,000 words of the body). A silver standard: the "
                  "article title names its main subject, so a good extractor should rank the title words high. "
                  "Words are compared after Porter stemming, for every system alike.", ""]
        lines += render_scores(e, [("title_recall", "title recall@10"), ("hit", "hit@10"), ("mrr", "MRR")], "mrr", False)
    if "summaries" in ex:
        e = ex["summaries"]
        lines += ["## 4. Summaries", "",
                  f"{e['articles']} Wikipedia articles: each system summarises the body (first 3,000 words) and is "
                  "scored against the article's human-written lead section with ROUGE F1 (`rouge-score`, Porter "
                  "stemming). Every summary is cut to the same word budget (the lead's length, at most 150 words).", ""]
        lines += render_scores(e, [("rouge1", "ROUGE-1"), ("rouge2", "ROUGE-2"), ("rougeL", "ROUGE-L")], "rouge1", False)
    if "performance" in ex:
        lines += ["## 5. Performance", "",
                  "Real speech transcripts: State of the Union addresses joined in chronological order and cut at "
                  "each size. `analyze()` is the whole text analysis; *full export* also writes all 11 files. Each "
                  "run starts with a cold term cache, like a new recording; sizes up to 100k words get one warm-up "
                  "run first. Whisper transcription is not included (see Limitations).", ""]
        lines += render_performance(ex["performance"])
    if "asr" in ex:
        lines += ["## 6. Speech recognition", "",
                  "Real recorded speech: LibriVox audiobook utterances (read speech), a two-speaker telephone "
                  "conversation with a time-stamped transcript, and untranscribed speech used only for speed. "
                  "Word error rate (WER) = (substitutions + deletions + insertions) / reference words, after the "
                  "same normalisation for every engine (lower case, no punctuation, \"mr\" = \"mister\", "
                  "digits as words).", ""]
        lines += render_asr(ex["asr"])
    if "parallel" in ex:
        lines += ["## 7. Parallel processing", "",
                  "`audio_brief/parallel.py` runs recognition in worker processes (recognition keeps Python's "
                  "GIL, so threads do not help: 2 PocketSphinx threads ran 1.02x faster than one), schedules the "
                  "longest work first, splits long recordings at pauses when workers would otherwise idle, and "
                  "analyses finished recordings while the others are still being transcribed.", ""]
        lines += render_parallel(ex["parallel"])
    if "synthetic" in ex:
        lines += ["## 8. Controlled stress tests (synthetic)", "",
                  "Generated conversations with exact ground truth for specific failure modes (generic words "
                  "shared by every topic, no punctuation, verbatim repetition). They complement the real-data "
                  "results above and are not evidence of real-world quality on their own.", ""]
        lines += render_synthetic(ex["synthetic"]["rows"])
    lines += ["## Limitations", "",
              "- Text experiments use clean text: recognition errors are measured separately (section 6) and "
              "not propagated into the text results. Whisper is only measured where its weights can be downloaded "
              "or are cached; otherwise the report says so.",
              "- Wikipedia and Usenet are written text. The multi-topic transcripts are *compositions* of real "
              "sentences (a standard method, Choi 2000), not recorded conversations.",
              "- The Usenet sample has only two topics; the keyword *subject* test uses titles as a silver standard.",
              "- Timings depend on the machine (see Environment); compare runs from the same machine. On the "
              "shared virtual machine that produced this file, repeated runs of the same speech-recognition "
              "measurement differed by up to about 30%; the long-file figure is a single run.",
              "", "## Reproduce", "", "```bash", "make bench          # full run, writes this file and results.json",
              "make bench-quick    # small run, printed only", "```", ""]
    return "\n".join(lines)


def _merge_partial(res: dict, raw: Path, only: set[str], quick: bool) -> dict:
    """``--only`` re-measures some experiments: keep the others from the existing
    results.json (same quick/full mode) instead of replacing the whole report, and
    record when the re-measured ones were taken."""
    if only >= set(EXPERIMENTS) or not raw.exists():
        return res
    old = json.loads(raw.read_text())
    if old.get("quick") != quick:
        print(f"    note: {raw.name} holds a {'quick' if old.get('quick') else 'full'} run; replacing it", flush=True)
        return res
    for name, exp in res["experiments"].items():
        if isinstance(exp, dict):
            exp["measured_at"] = res["generated"]
            exp["environment"] = res["environment"]
        old["experiments"][name] = exp
    old["config"].update(res["config"])
    print(f"    merged {', '.join(sorted(res['experiments']))} into the existing {raw.name}", flush=True)
    return old


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true", help="few trials and small sizes")
    parser.add_argument("--only", default=",".join(EXPERIMENTS), help=f"comma list of: {', '.join(EXPERIMENTS)}")
    parser.add_argument("--out", default=str(HERE / "RESULTS.md"))
    parser.add_argument("--render-only", action="store_true", help="rebuild the report from results.json")
    args = parser.parse_args(argv)
    out = Path(args.out)
    raw = out.with_name(out.stem.replace("RESULTS", "results") + ".json") if out.name == "RESULTS.md" \
        else out.with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    if args.render_only:
        res = json.loads(raw.read_text())
    else:
        only = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = only - set(EXPERIMENTS)
        if unknown:
            print(f"unknown experiment(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        res = collect(args.quick, only)
        res = _merge_partial(res, raw, only, args.quick)
        raw.write_text(json.dumps(res, indent=1))
    out.write_text(render(res), encoding="utf-8")
    print(f"==> wrote {out} and {raw.name} in {time.perf_counter() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
