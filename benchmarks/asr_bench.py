"""Speech-recognition benchmark: accuracy (WER) and cost (speed, memory, size).

Every engine runs in its own subprocess so its peak memory (model included) is
measured cleanly. Items come from ``fetch_data.prepare_asr``; see
METHODOLOGY.md section 2.6.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import stats

DATA = Path(__file__).with_name("data") / "asr"
CANDIDATES = [("pocketsphinx", None), ("whisper", "tiny"), ("whisper", "base")]

# --- text normalisation (the same for every engine) ------------------------------------------

_ABBREV = {"mr": "mister", "mrs": "missus", "dr": "doctor", "ok": "okay", "st": "saint"}
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen " \
        "sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _number_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _number_words(n % 100))
    if n < 1_000_000:
        return _number_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _number_words(n % 1000))
    return str(n)


def normalize(text: str) -> str:
    """Lowercase, drop punctuation (keeping apostrophes inside words), expand a few
    abbreviations and write numbers as words, so "Mr. Smith, 10" == "mister smith ten"."""
    text = text.lower().replace("-", " ")
    text = re.sub(r"\d+", lambda m: " " + _number_words(int(m.group())) + " ", text)
    words = re.findall(r"[a-z]+(?:'[a-z]+)*", text)
    return " ".join(_ABBREV.get(w, w) for w in words)


def edits(ref: str, hyp: str) -> tuple[int, int]:
    """(word-level edit distance, reference length) after normalisation."""
    r, h = normalize(ref).split(), normalize(hyp).split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
    return d[len(h)], len(r)


def corpus_wer_ci(pairs: list[tuple[int, int]], seed: int = 0) -> dict:
    """Corpus WER (sum of edits / sum of words) with an item-bootstrap 95% CI."""
    total = sum(e for e, _ in pairs) / max(1, sum(n for _, n in pairs))
    rnd = random.Random(seed)
    boots = []
    for _ in range(stats.RESAMPLES):
        sample = rnd.choices(pairs, k=len(pairs))
        boots.append(sum(e for e, _ in sample) / max(1, sum(n for _, n in sample)))
    boots.sort()
    return {"wer": total, "lo": boots[int(0.025 * len(boots))], "hi": boots[int(0.975 * len(boots)) - 1],
            "items": len(pairs), "words": sum(n for _, n in pairs)}


# --- availability --------------------------------------------------------------------------------

def availability(engine: str, model: str | None) -> tuple[bool, str]:
    module = "whisper" if engine == "whisper" else "pocketsphinx"
    if importlib.util.find_spec(module) is None:
        return False, f"{module} not installed"
    if engine != "whisper":
        return True, "bundled en-us model"
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "whisper" / f"{model}.pt"
    if cache.exists():
        return True, f"cached weights {cache}"
    try:
        import urllib.request

        import whisper

        url = whisper._MODELS[model]
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=8)
        return True, "weights downloadable"
    except Exception as exc:  # no network / blocked host
        return False, f"model weights not cached and not downloadable ({type(exc).__name__})"


# --- running an engine in a child process -------------------------------------------------------

_CHILD = r'''
import json, resource, sys, time
from audio_brief import asr
engine, model, files = sys.argv[1], (sys.argv[2] or None), sys.argv[3:]
t0 = time.perf_counter(); eng = asr.load(engine, model); load_s = time.perf_counter() - t0
out = []
for f in files:
    t0 = time.perf_counter(); r = eng.transcribe(f, "en"); dt = time.perf_counter() - t0
    out.append({"file": f, "text": r["text"], "segments": len(r["segments"]), "duration": r["duration"], "decode_s": dt})
# Peak memory of THIS process. On Linux ru_maxrss survives fork+exec (a child
# "inherits" its parent's peak), so read VmHWM, which starts fresh at exec.
try:
    rss = next(int(l.split()[1]) * 1024 for l in open("/proc/self/status") if l.startswith("VmHWM:"))
except OSError:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # macOS: bytes
print(json.dumps({"load_s": load_s, "results": out, "peak_rss_bytes": rss}))
'''


def run_engine(engine: str, model: str | None, files: list[Path], timeout: int = 3600) -> dict:
    root = Path(__file__).resolve().parent.parent
    proc = subprocess.run([sys.executable, "-c", _CHILD, engine, model or "", *map(str, files)],
                          capture_output=True, text=True, timeout=timeout, cwd=root,
                          env={**os.environ, "PYTHONPATH": str(root)})
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "engine failed")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _cut(src: Path, start: float, end: float, dest: Path) -> Path:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-ac", "1", "-ar", "16000", str(dest)], check=True)
    return dest


def _concat(files: list[Path], minutes: float, dest: Path) -> Path:
    listing = dest.with_suffix(".txt")
    total, lines = 0.0, []
    durations = {f: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout)
                 for f in files}
    while total < minutes * 60:
        for f in files:
            lines.append(f"file '{f}'")
            total += durations[f]
            if total >= minutes * 60:
                break
    listing.write_text("\n".join(lines))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-t", f"{minutes * 60:.0f}", "-ac", "1", "-ar", "16000", str(dest)], check=True)
    return dest


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def footprint() -> dict:
    """Disk size of each engine's installed packages (and cached Whisper weights)."""
    import site

    sites = [Path(p) for p in site.getsitepackages()]
    out = {}
    for name, dirs in (("pocketsphinx", ["pocketsphinx"]),
                       ("whisper", ["whisper", "torch", "nvidia", "triton", "cuda", "torchgen"])):
        size = 0
        for s in sites:
            for d in dirs:
                if (s / d).exists():
                    size += _dir_size(s / d)
        out[name] = size
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "whisper"
    out["whisper_weights_cached"] = _dir_size(cache) if cache.exists() else 0
    return out


def benchmark(log, long_minutes: float = 10.0) -> dict:
    if not shutil.which("ffmpeg"):
        raise SystemExit("the ASR benchmark needs ffmpeg")
    items = json.loads((DATA / "items.json").read_text())
    engines = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        read = [i for i in items if i["kind"] == "read speech"]
        conv = next(i for i in items if i["id"] == "conversation")
        turn_files = [_cut(DATA / conv["audio"], t["start"], t["end"], tmp / f"turn_{k:02d}.wav")
                      for k, t in enumerate(conv["turns"])]
        untranscribed = [DATA / i["audio"] for i in items if i["reference"] is None]
        long_file = _concat([DATA / i["audio"] for i in items], long_minutes, tmp / "long.wav")
        for engine, model in CANDIDATES:
            label = engine if model is None else f"{engine} {model}"
            ok, why = availability(engine, model)
            if not ok:
                log(f"asr: {label}: skipped ({why})")
                engines.append({"engine": label, "available": False, "reason": why})
                continue
            res = run_engine(engine, model, [DATA / i["audio"] for i in read] + turn_files
                             + [DATA / conv["audio"]] + untranscribed)
            by_file = {Path(r["file"]).name: r for r in res["results"]}
            read_pairs = [edits(i["reference"], by_file[i["audio"]]["text"]) for i in read]
            turn_pairs = [edits(t["text"], by_file[f.name]["text"]) for t, f in zip(conv["turns"], turn_files)]
            whole = edits(conv["reference"], by_file[conv["audio"]]["text"])
            timed = [by_file[f.name] for f in [DATA / conv["audio"], *untranscribed]]
            rtf = [r["decode_s"] / r["duration"] for r in timed if r["duration"]]
            long_run = run_engine(engine, model, [long_file])
            lr = long_run["results"][0]
            entry = {
                "engine": label, "available": True, "detail": why,
                "wer_read": corpus_wer_ci(read_pairs), "wer_conversation_turns": corpus_wer_ci(turn_pairs),
                "wer_conversation_whole": {"wer": whole[0] / max(1, whole[1]), "words": whole[1]},
                "wer_all": corpus_wer_ci(read_pairs + turn_pairs),
                "load_s": res["load_s"], "rtf_median": stats.quantiles(rtf)["median"], "rtf_files": len(rtf),
                "long": {"audio_s": lr["duration"], "decode_s": lr["decode_s"], "rtf": lr["decode_s"] / lr["duration"],
                         "peak_rss_bytes": long_run["peak_rss_bytes"]},
                "examples": {i["id"]: {"reference": i["reference"], "hypothesis": by_file[i["audio"]]["text"]}
                             for i in read[:2]} | {"conversation": {"reference": conv["reference"][:300],
                                                                     "hypothesis": by_file[conv["audio"]]["text"][:300]}},
            }
            engines.append(entry)
            log(f"asr: {label}: WER {entry['wer_all']['wer']:.1%} on {entry['wer_all']['words']} words, "
                f"RTF {entry['rtf_median']:.2f}, {long_minutes:.0f}-min file in {lr['decode_s']:.0f}s, "
                f"peak memory {long_run['peak_rss_bytes'] / 1e6:.0f} MB")
    total_audio = sum(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                            "csv=p=0", str(DATA / i["audio"])], capture_output=True, text=True).stdout)
                      for i in items)
    return {"items": len(items), "reference_words": sum(len(normalize(i["reference"] or "").split()) for i in items),
            "audio_s": total_audio, "long_minutes": long_minutes, "engines": engines, "footprint": footprint()}
