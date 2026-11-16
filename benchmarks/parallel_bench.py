"""Parallel-processing benchmark: speed-up and the accuracy cost of splitting.

1. Batch: the same files with one worker vs the automatic plan (wall time).
2. Long file: one recording made only of *transcribed* speech (the read
   utterances and the conversation, repeated) so its full reference transcript
   is known; recognised whole with one worker vs split at pauses across
   workers. Recognition is deterministic, so a WER difference is caused by the
   splitting itself.

PocketSphinx only: Whisper needs model weights (see asr_bench.availability).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from audio_brief import parallel

from . import asr_bench


def _timed_run(files: list[Path], jobs, split: bool) -> tuple[float, dict, parallel.Plan]:
    plan = parallel.make_plan(files, "pocketsphinx", None, jobs=jobs, split=split)
    results: dict[int, dict] = {}
    t0 = time.perf_counter()
    outcome = parallel.run(plan, files, "pocketsphinx", None, "en", lambda i, r, s: results.__setitem__(i, r),
                           log=lambda m: None)
    if outcome.failed:  # never report timings of a run that did not do the work
        raise RuntimeError(f"parallel run failed: {next(iter(outcome.failed.values()))}")
    return time.perf_counter() - t0, results, plan


def _long_transcribed(tmp: Path, minutes: float) -> tuple[Path, str]:
    items = [i for i in json.loads((asr_bench.DATA / "items.json").read_text()) if i["reference"]]
    lines, refs, total = [], [], 0.0
    while total < minutes * 60:
        for it in items:
            lines.append(f"file '{asr_bench.DATA / it['audio']}'")
            refs.append(it["reference"])
            total += parallel.probe_duration(asr_bench.DATA / it["audio"])
    listing = tmp / "list.txt"
    listing.write_text("\n".join(lines))
    dest = tmp / "long_transcribed.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-ac", "1", "-ar", "16000", str(dest)], check=True)
    return dest, " ".join(refs)


def benchmark(log, long_minutes: float = 4.0, quick: bool = False) -> dict:
    ok, why = asr_bench.availability("pocketsphinx", None)
    if not ok:
        log(f"parallel: skipped ({why})")
        return {"available": False, "reason": why}
    cpus, mem = parallel.system_resources()
    items = json.loads((asr_bench.DATA / "items.json").read_text())
    batch = [asr_bench.DATA / i["audio"] for i in items]
    if quick:
        batch = [asr_bench.DATA / "speech_60s.wav", asr_bench.DATA / "conversation.wav",
                 asr_bench.DATA / "librivox_0870.wav"]
    out = {"available": True, "cpus": cpus, "memory_gb": mem}
    audio = sum(parallel.probe_duration(f) for f in batch)
    seq_s, _, _ = _timed_run(batch, 1, False)
    par_s, _, plan = _timed_run(batch, "auto", True)
    out["batch"] = {"files": len(batch), "audio_s": audio, "sequential_s": seq_s, "parallel_s": par_s,
                    "workers": plan.workers, "units": len(plan.units), "speedup": seq_s / par_s}
    log(f"parallel: batch of {len(batch)} files ({audio:.0f}s audio): 1 worker {seq_s:.0f}s, "
        f"{plan.workers} workers {par_s:.0f}s ({seq_s / par_s:.1f}x)")
    with tempfile.TemporaryDirectory() as tmp:
        long_file, reference = _long_transcribed(Path(tmp), long_minutes)
        length = parallel.probe_duration(long_file)
        whole_s, whole, _ = _timed_run([long_file], 1, False)
        split_s, parts, splan = _timed_run([long_file], "auto", True)
        e_whole, n = asr_bench.edits(reference, whole[0]["text"])
        e_split, _ = asr_bench.edits(reference, parts[0]["text"])
        diff, _ = asr_bench.edits(whole[0]["text"], parts[0]["text"])
    out["long"] = {"audio_s": length, "reference_words": n, "whole_s": whole_s, "split_s": split_s,
                   "parts": len(splan.units), "workers": splan.workers, "speedup": whole_s / split_s,
                   "wer_whole": e_whole / n, "wer_split": e_split / n,
                   "transcripts_differ": diff / max(1, len(asr_bench.normalize(whole[0]["text"]).split()))}
    log(f"parallel: long file {length:.0f}s: whole {whole_s:.0f}s (WER {e_whole / n:.1%}), split into "
        f"{len(splan.units)} parts {split_s:.0f}s (WER {e_split / n:.1%}), {whole_s / split_s:.1f}x faster")
    return out
