"""Small, dependency-free statistics for benchmark reporting.

* ``ci``: mean with a percentile-bootstrap 95% confidence interval.
* ``paired``: mean difference between two systems measured on the same
  trials, its bootstrap CI, win/tie/loss counts and a verdict: "better" or
  "worse" only when the CI excludes 0 (and there are >= 10 trials),
  otherwise "no clear difference".
* ``quantiles``/``loglog_fit`` for timing: medians, IQR and the scaling
  exponent b of time ~ a * words^b.

All resampling is seeded, so reports are reproducible.
"""

from __future__ import annotations

import math
import random
import statistics

RESAMPLES = 2000
# Bootstrap intervals from a handful of trials are unreliable: no verdict below this.
MIN_TRIALS_FOR_VERDICT = 10


def ci(values: list[float], level: float = 0.95, seed: int = 0) -> dict:
    vals = [float(v) for v in values]
    if not vals:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0, "sd": float("nan")}
    mean = statistics.fmean(vals)
    if len(vals) == 1:
        return {"mean": mean, "lo": mean, "hi": mean, "n": 1, "sd": 0.0}
    rnd = random.Random(seed)
    n = len(vals)
    means = sorted(statistics.fmean(rnd.choices(vals, k=n)) for _ in range(RESAMPLES))
    alpha = (1 - level) / 2
    return {"mean": mean, "lo": means[int(alpha * RESAMPLES)], "hi": means[int((1 - alpha) * RESAMPLES) - 1],
            "n": n, "sd": statistics.stdev(vals)}


def paired(ours: list[float], other: list[float], seed: int = 0, higher_is_better: bool = True) -> dict:
    assert len(ours) == len(other), "paired comparison needs the same trials"
    diffs = [a - b for a, b in zip(ours, other)]
    stat = ci(diffs, seed=seed)
    eps = 1e-12
    wins = sum(1 for d in diffs if (d > eps if higher_is_better else d < -eps))
    losses = sum(1 for d in diffs if (d < -eps if higher_is_better else d > eps))
    if len(diffs) < MIN_TRIALS_FOR_VERDICT:
        verdict = f"too few trials (<{MIN_TRIALS_FOR_VERDICT})"
    elif stat["lo"] > 0:
        verdict = "better" if higher_is_better else "worse"
    elif stat["hi"] < 0:
        verdict = "worse" if higher_is_better else "better"
    else:
        verdict = "no clear difference"
    return {"diff": stat["mean"], "lo": stat["lo"], "hi": stat["hi"], "wins": wins, "losses": losses,
            "ties": len(diffs) - wins - losses, "verdict": verdict}


def quantiles(values: list[float]) -> dict:
    vals = sorted(values)
    if len(vals) == 1:
        return {"median": vals[0], "p25": vals[0], "p75": vals[0], "min": vals[0], "max": vals[0]}
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return {"median": statistics.median(vals), "p25": q[0], "p75": q[2], "min": vals[0], "max": vals[-1]}


def loglog_fit(xs: list[float], ys: list[float]) -> dict:
    """Least-squares fit of log(y) = log(a) + b log(x); returns b and R^2."""
    lx, ly = [math.log(x) for x in xs], [math.log(y) for y in ys]
    mx, my = statistics.fmean(lx), statistics.fmean(ly)
    sxx = sum((x - mx) ** 2 for x in lx)
    b = sum((x - mx) * (y - my) for x, y in zip(lx, ly)) / sxx
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(lx, ly))
    ss_tot = sum((y - my) ** 2 for y in ly)
    return {"exponent": b, "r2": 1 - ss_res / ss_tot if ss_tot else 1.0}
