"""Parallel transcription and analysis of many (or long) recordings.

Speech recognition is CPU-bound code that keeps Python's GIL (measured for
PocketSphinx: 2 threads = 1.02x), and Whisper models are not safe to share
between threads, so recognition runs in worker **processes**, each loading its
engine once. Threads are used where they help: probing durations and looking
for pauses, which wait on ffprobe/ffmpeg.

The plan (``make_plan``) decides, and explains:

* how many workers: CPU cores, available memory and the engine's footprint;
* for Whisper, how many PyTorch threads per worker (no CPU oversubscription);
* whether to split long files at pauses so idle workers can help (on by
  default for PocketSphinx, whose accuracy impact is measured in
  benchmarks/RESULTS.md; opt-in for Whisper, where it is not measured);
* the order: longest work first (LPT scheduling).

``run`` executes it: while workers transcribe, the main process analyses and
writes each recording as soon as all its pieces are back.
"""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import asr

# Peak memory per worker process, model included (GB). PocketSphinx: measured
# (169 MB, benchmarks/RESULTS.md). Whisper: the model sizes published by OpenAI
# ("required VRAM"), used as the CPU-RAM estimate; not measured here.
MEMORY_GB = {"pocketsphinx": 0.25, "tiny": 1.0, "base": 1.0, "small": 2.0,
             "medium": 5.0, "large": 10.0, "turbo": 6.0}
MIN_CHUNK_S = 60.0
MAX_CHUNK_S = 600.0


@dataclass
class Unit:
    """One piece of work: a whole file, or a part of a long one."""
    file_index: int
    path: Path
    start: float
    end: float
    part: int = 0
    parts: int = 1

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    workers: int
    torch_threads: int | None
    split: bool
    chunk_s: float
    durations: list[float]
    units: list[Unit]
    reasons: list[str] = field(default_factory=list)

    def describe(self, files: list[Path], engine: str) -> str:
        total = sum(self.durations)
        split_files = len({u.file_index for u in self.units if u.parts > 1})
        lines = [f"Plan: {len(files)} file(s), {_hms(total)} of audio, engine {engine}: "
                 f"{self.workers} worker process(es)"
                 + (f" x {self.torch_threads} PyTorch thread(s)" if self.torch_threads else "")
                 + f", {len(self.units)} unit(s) of work, longest first"]
        if split_files:
            lines.append(f"  {split_files} long file(s) split at pauses into parts of about {_hms(self.chunk_s)}")
        lines += [f"  - {r}" for r in self.reasons]
        return "\n".join(lines)


def _hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


# --- system and audio probing ---------------------------------------------------------------

def system_resources() -> tuple[int, float]:
    """(usable CPU cores, available memory in GB)."""
    try:
        cpus = len(os.sched_getaffinity(0))
    except AttributeError:  # macOS
        cpus = os.cpu_count() or 1
    avail = None
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) / 1024 / 1024
                break
    except OSError:
        pass
    if avail is None:  # macOS: assume half of physical memory is free
        try:
            avail = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3 / 2
        except (ValueError, OSError, AttributeError):
            avail = 4.0
    return cpus, avail


def probe_duration(path: Path) -> float:
    """Audio length in seconds via ffprobe (0.0 if unknown)."""
    if not shutil.which("ffprobe"):
        return 0.0
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def find_pauses(path: Path, noise_db: int = -35, min_pause_s: float = 0.3) -> list[float]:
    """Midpoints of the pauses in a recording (ffmpeg's silencedetect filter)."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
                           f"silencedetect=noise={noise_db}dB:d={min_pause_s}", "-f", "null", "-"],
                          capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", proc.stderr)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def cut_points(duration: float, chunk_s: float, pauses: list[float]) -> list[float]:
    """Boundaries near every ``chunk_s`` seconds, moved to the nearest pause within
    25% of a chunk (so words are not cut); a hard cut if there is no pause."""
    n = max(1, round(duration / chunk_s))
    cuts = []
    for k in range(1, n):
        target = k * duration / n
        near = [p for p in pauses if abs(p - target) <= 0.25 * chunk_s and (not cuts or p > cuts[-1] + 1)]
        cuts.append(min(near, key=lambda p: abs(p - target)) if near else target)
    return cuts


def make_plan(files: list[Path], engine: str, model: str | None, jobs: str | int = "auto",
              split: bool | None = None, resources: tuple[int, float] | None = None,
              durations: list[float] | None = None) -> Plan:
    """Decide workers, threads, splitting and order; every decision gets a reason."""
    cpus, mem_gb = resources or system_resources()
    reasons = []
    if durations is None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(files) or 1)) as pool:
            durations = list(pool.map(probe_duration, files))  # I/O-bound: threads are right here
    per_worker = MEMORY_GB["pocketsphinx" if engine == "pocketsphinx" else (model or "base")]
    threads_each = 1 if engine == "pocketsphinx" else max(1, min(4, cpus // 2))
    by_cpu = max(1, cpus // threads_each)
    by_mem = max(1, int(0.8 * mem_gb // per_worker))
    if jobs == "auto":
        cap = min(by_cpu, by_mem)
        reasons.append(f"{cpus} CPU core(s) and {mem_gb:.1f} GB available; ~{per_worker:g} GB per {engine} worker "
                       f"-> at most {cap} worker(s) (CPU allows {by_cpu}, memory {by_mem})")
    else:
        cap = max(1, int(jobs))
        reasons.append(f"--jobs {cap} requested")
        if cap > by_mem:
            reasons.append(f"warning: {cap} workers may need ~{cap * per_worker:g} GB, only {mem_gb:.1f} GB available")

    if split is None:
        split = engine == "pocketsphinx"
        reasons.append("long files are split at pauses" if split else
                       "long files are not split (Whisper: accuracy effect not measured; use --split-long)")
    total = sum(durations)
    chunk_s = min(MAX_CHUNK_S, max(MIN_CHUNK_S, total / max(1, 2 * cap))) if total else MAX_CHUNK_S
    units: list[Unit] = []
    split_candidates = [i for i, d in enumerate(durations) if split and d > 1.5 * chunk_s]
    if split_candidates and (len(files) < cap or max(durations) > 2 * total / max(1, cap)):
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(split_candidates))) as pool:
            pauses = dict(zip(split_candidates, pool.map(lambda i: find_pauses(files[i]), split_candidates)))
    else:
        pauses = {}
    for i, (path, d) in enumerate(zip(files, durations)):
        if i in pauses:
            edges = [0.0, *cut_points(d, chunk_s, pauses[i]), d]
            parts = len(edges) - 1
            units += [Unit(i, path, edges[k], edges[k + 1], k, parts) for k in range(parts)]
        else:
            units.append(Unit(i, path, 0.0, d))
    units.sort(key=lambda u: -u.duration)  # longest first (LPT)
    workers = max(1, min(cap, len(units)))
    if workers < cap:
        reasons.append(f"{len(units)} unit(s) of work, so {workers} worker(s) are enough")
    torch_threads = None
    if engine == "whisper":
        torch_threads = max(1, cpus // workers)
        reasons.append(f"{torch_threads} PyTorch thread(s) per worker so {workers} worker(s) share {cpus} cores "
                       "without oversubscription")
    return Plan(workers, torch_threads, bool(pauses), chunk_s, durations, units, reasons)


# --- worker side -----------------------------------------------------------------------------

_ENGINE: Any = None


def _init_worker(engine: str, model: str | None, torch_threads: int | None) -> None:
    global _ENGINE
    if torch_threads:
        for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[var] = str(torch_threads)
        try:
            import torch

            torch.set_num_threads(torch_threads)
        except ImportError:
            pass
    _ENGINE = asr.load(engine, model)


def _transcribe_unit(unit: Unit, language: str | None) -> dict:
    """Runs in a worker: cut the unit if it is a part, transcribe it, time it."""
    t0 = time.perf_counter()
    if unit.parts == 1:
        result = _ENGINE.transcribe(unit.path, language)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            piece = Path(tmp) / "part.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{unit.start:.3f}", "-to",
                            f"{unit.end:.3f}", "-i", str(unit.path), "-ac", "1", "-ar", "16000", str(piece)], check=True)
            result = _ENGINE.transcribe(piece, language)
    return {"result": result, "seconds": time.perf_counter() - t0}


def merge(parts: list[tuple[Unit, dict]]) -> dict:
    """Join the parts of one file: segments shifted by the part's start time."""
    parts = sorted(parts, key=lambda p: p[0].part)
    segments = [{**s, "start": round(s["start"] + u.start, 2), "end": round(s["end"] + u.start, 2)}
                for u, r in parts for s in r["segments"]]
    return {"text": " ".join(r["text"].strip() for _, r in parts if r["text"].strip()), "segments": segments,
            "language": parts[0][1].get("language"), "duration": parts[-1][0].end or
            sum(r.get("duration") or 0.0 for _, r in parts)}


@dataclass
class Outcome:
    ok: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)
    wall_s: float = 0.0
    busy_s: float = 0.0  # summed recognition time of all units, across workers
    audio_s: float = 0.0


def run(plan: Plan, files: list[Path], engine: str, model: str | None, language: str | None,
        on_file_done: Callable[[int, dict, float], None], log: Callable[[str], None] = print,
        executor: str = "process") -> Outcome:
    """Execute a plan. ``on_file_done(index, result, recognition_seconds)`` runs in
    this process as soon as every part of a file is transcribed (analysis and
    writing overlap with the remaining recognition). ``executor="thread"`` is
    for tests (same process, no parallel speed-up)."""
    t0 = time.perf_counter()
    out = Outcome(audio_s=sum(plan.durations))
    pending: dict[int, list[tuple[Unit, dict]]] = {}
    spent: dict[int, float] = {}
    need = {i: sum(1 for u in plan.units if u.file_index == i) for i in range(len(files))}
    if executor == "process":
        pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=plan.workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker, initargs=(engine, model, plan.torch_threads))
    else:
        _init_worker(engine, model, None)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=plan.workers)
    done_audio = 0.0
    with pool:
        futures = {pool.submit(_transcribe_unit, u, language): u for u in plan.units}
        for fut in concurrent.futures.as_completed(futures):
            unit = futures[fut]
            i = unit.file_index
            if i in out.failed:
                continue
            try:
                got = fut.result()
            except Exception as exc:  # one bad file must not stop the others
                out.failed[i] = f"{type(exc).__name__}: {exc}"
                log(f"  x {files[i].name}: {out.failed[i]}")
                continue
            out.busy_s += got["seconds"]
            spent[i] = spent.get(i, 0.0) + got["seconds"]
            pending.setdefault(i, []).append((unit, got["result"]))
            done_audio += unit.duration
            elapsed = time.perf_counter() - t0
            rate = done_audio / elapsed if elapsed else 0.0
            eta = (out.audio_s - done_audio) / rate if rate else 0.0
            part = f" part {unit.part + 1}/{unit.parts}" if unit.parts > 1 else ""
            log(f"  [{_hms(elapsed)}] {files[i].name}{part}: {_hms(unit.duration)} of audio in "
                f"{got['seconds']:.0f}s; {100 * done_audio / max(out.audio_s, 1e-9):.0f}% of all audio done, "
                f"ETA {_hms(eta)}")
            if len(pending[i]) == need[i]:
                try:
                    on_file_done(i, merge(pending.pop(i)), spent[i])
                    out.ok.append(i)
                except Exception as exc:
                    out.failed[i] = f"{type(exc).__name__}: {exc}"
                    log(f"  x {files[i].name}: {out.failed[i]}")
    out.wall_s = time.perf_counter() - t0
    return out


def summary(outcome: Outcome, plan: Plan) -> str:
    speed = outcome.audio_s / outcome.wall_s if outcome.wall_s else 0.0
    busy = outcome.busy_s / outcome.wall_s if outcome.wall_s else 0.0
    return (f"\nParallel run: {len(outcome.ok)} file(s) done, {len(outcome.failed)} failed; "
            f"{_hms(outcome.audio_s)} of audio in {_hms(outcome.wall_s)} wall time ({speed:.1f}x real time) "
            f"with {plan.workers} worker(s), on average {busy:.1f} of them busy. (Measured speed-ups over a "
            "single worker: benchmarks/RESULTS.md.)")
