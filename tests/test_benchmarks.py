"""Benchmark smoke tests.

The synthetic part always runs. The real-corpus part needs the optional
``[bench]`` packages and the downloaded data (``make bench-data``); without
them it is skipped with the reason shown by ``pytest -ra``.
"""

import importlib.util
import re
from pathlib import Path

import pytest

from benchmarks import run, stats

DATA = Path(run.__file__).with_name("data") / "manifest.json"
BENCH_MODULES = ("yake", "summa", "sumy", "rouge_score", "sklearn", "nltk")


def test_synthetic_benchmark_renders_report(tmp_path):
    out = tmp_path / "RESULTS.md"
    assert run.main(["--quick", "--only", "synthetic", "--out", str(out)]) == 0
    content = out.read_text(encoding="utf-8")
    assert content.startswith("# Benchmark results")
    assert "Controlled stress tests (synthetic)" in content
    assert (tmp_path / "results.json").exists()
    assert all(0 <= int(p) <= 100 for p in re.findall(r"\| (\d+)% ", content))


@pytest.mark.skipif(not DATA.exists(), reason="benchmark data not downloaded (make bench-data)")
@pytest.mark.skipif(any(importlib.util.find_spec(m) is None for m in BENCH_MODULES),
                    reason="[bench] extras not installed (make bench-env)")
def test_quick_real_benchmark_renders_every_section(tmp_path):
    out = tmp_path / "RESULTS.md"
    assert run.main(["--quick", "--only", "topics,keywords,summaries", "--out", str(out)]) == 0
    content = out.read_text(encoding="utf-8")
    for heading in ("## 1. Topic discovery", "## 2. Topic tree quality", "## 3. Keywords", "## 4. Summaries"):
        assert heading in content
    assert "too few trials" in content  # quick mode never claims a verdict


def test_only_merges_into_existing_results_instead_of_replacing_them(tmp_path):
    import json

    out = tmp_path / "RESULTS.md"
    raw = tmp_path / "results.json"
    raw.write_text(json.dumps({"generated": "2000-01-01T00:00:00", "quick": True, "config": {"trials": 3},
                               "environment": {"os": "elsewhere"}, "data": {"sources": {}, "datasets": {}},
                               "experiments": {"kept": {"value": 1}}}))
    assert run.main(["--quick", "--only", "synthetic", "--out", str(out)]) == 0
    res = json.loads(raw.read_text())
    assert res["experiments"]["kept"] == {"value": 1}  # the other experiment survives
    assert res["generated"] == "2000-01-01T00:00:00"
    assert res["experiments"]["synthetic"]["measured_at"] > res["generated"]
    text = out.read_text(encoding="utf-8")
    assert "Re-measured later with `--only`: synthetic on " in text and "on a different machine" in text


def test_stats_ci_and_paired():
    c = stats.ci([1.0] * 20)
    assert (c["mean"], c["lo"], c["hi"]) == (1.0, 1.0, 1.0)
    better = stats.paired([0.9] * 12, [0.5] * 12)
    assert better["verdict"] == "better" and better["wins"] == 12
    noisy = stats.paired([0.6, 0.4] * 6, [0.5, 0.5] * 6)
    assert noisy["verdict"] == "no clear difference"
    assert stats.paired([1.0] * 3, [0.0] * 3)["verdict"].startswith("too few trials")
    fit = stats.loglog_fit([1e3, 1e4, 1e5], [0.01, 0.1, 1.0])
    assert abs(fit["exponent"] - 1.0) < 1e-9 and fit["r2"] > 0.999


def test_metrics_on_a_perfect_and_a_bad_tree():
    from audio_brief.textproc import TopicNode
    from benchmarks import metrics

    topics = {"a": {"apple", "apricot"}, "b": {"banana", "blueberry"}}
    good = [TopicNode("apple", 3, [TopicNode("apricot", 2)]), TopicNode("banana", 3, [TopicNode("blueberry", 2)])]
    q = metrics.topic_tree_quality(good, topics)
    assert (q["coverage"], q["purity"], q["generic_roots"], q["fragmentation"]) == (1.0, 1.0, 0.0, 1.0)
    bad = [TopicNode("apple", 3, [TopicNode("banana", 2)]), TopicNode("needs", 5)]
    q = metrics.topic_tree_quality(bad, topics)
    assert (q["coverage"], q["purity"], q["generic_roots"]) == (0.0, 0.0, 0.5)


def test_composition_alignment_is_exact():
    from audio_brief import textproc
    from benchmarks import real

    arts = [{"title": f"T{i}", "sentences": [f"Topic {i} sentence number {j} is here." for j in range(50)]}
            for i in range(3)]
    comp = real.compose_articles(arts, 3, 20, seed=1)
    units = textproc.sentences(comp.text)
    unit_of = real.align(comp, units)
    assert all(units[u] == s for u, s in zip(unit_of, comp.sentences))


def test_asr_section_renders_measured_and_unavailable_engines():
    ci = {"wer": 0.3, "lo": 0.2, "hi": 0.4, "items": 5, "words": 70}
    exp = {"items": 8, "reference_words": 152, "audio_s": 283.0, "long_minutes": 5,
           "footprint": {"pocketsphinx": 39e6, "whisper": 5.5e9, "whisper_weights_cached": 0},
           "engines": [
               {"engine": "pocketsphinx", "available": True, "detail": "bundled en-us model", "wer_read": ci,
                "wer_conversation_turns": ci, "wer_conversation_whole": {"wer": 0.8, "words": 82}, "wer_all": ci,
                "load_s": 0.5, "rtf_median": 0.7, "rtf_files": 3,
                "long": {"audio_s": 300.0, "decode_s": 200.0, "rtf": 0.67, "peak_rss_bytes": 170e6},
                "examples": {"x": {"reference": "Hello there.", "hypothesis": "hello their"}}},
               {"engine": "whisper tiny", "available": False, "reason": "weights not downloadable"}]}
    text = "\n".join(run.render_asr(exp))
    assert "152 transcribed words" in text
    assert "| pocketsphinx | bundled en-us model | 30% [20, 40] |" in text
    assert "| whisper tiny | **not measured**: weights not downloadable |" in text
    assert "reference: hello there" in text and "recognised: hello their" in text


def test_parallel_section_renders_measurements_and_unavailability():
    exp = {"available": True, "cpus": 4, "memory_gb": 15.0,
           "batch": {"files": 8, "audio_s": 284.0, "sequential_s": 148.0, "parallel_s": 38.0, "workers": 4,
                     "units": 10, "speedup": 3.9},
           "long": {"audio_s": 274.0, "reference_words": 760, "whole_s": 150.0, "split_s": 55.0, "parts": 5,
                    "workers": 4, "speedup": 2.7, "wer_whole": 0.605, "wer_split": 0.574,
                    "transcripts_differ": 0.29}}
    text = "\n".join(run.render_parallel(exp))
    assert "| 148 s | 38 s (4 workers, 10 units) | **3.9x** |" in text
    assert "2 extra unit(s): long files were split" in text
    assert "whole 60.5% vs split 57.4% (760 reference words)" in text
    assert "29% of words differ" in text
    gone = "\n".join(run.render_parallel({"available": False, "reason": "pocketsphinx not installed"}))
    assert gone.startswith("Not measured: pocketsphinx not installed")


def test_asr_normalisation_and_wer():
    from benchmarks import asr_bench as ab

    assert ab.normalize("Mr. Smith paid $10, OK?") == "mister smith paid ten okay"
    assert ab.edits("he was not an ill disposed young man", "he was not until this blows young man") == (3, 8)
    ci = ab.corpus_wer_ci([(1, 10), (3, 10)])
    assert ci["wer"] == 0.2 and ci["lo"] <= 0.2 <= ci["hi"]
