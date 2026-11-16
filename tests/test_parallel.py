"""Parallel transcription planning and execution (audio_brief/parallel.py).

Plans are tested with injected CPU/memory/durations so they are deterministic
on any machine. Execution is tested with threads and a fake engine (same
process), plus one real multi-process run with PocketSphinx when installed.
"""

import functools
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from audio_brief import asr, cli, parallel

WAV = Path(__file__).with_name("data") / "librivox_sense_and_sensibility_0880.wav"


def _plan(durations, engine="pocketsphinx", model=None, jobs="auto", split=None, cpus=8, mem=16.0, pauses=None,
          monkeypatch=None):
    files = [Path(f"f{i}.wav") for i in range(len(durations))]
    if monkeypatch is not None:
        monkeypatch.setattr(parallel, "find_pauses", lambda path: pauses or [])
    return parallel.make_plan(files, engine, model, jobs=jobs, split=split, resources=(cpus, mem),
                              durations=durations), files


def test_workers_follow_cpu_memory_and_work(monkeypatch):
    plan, _ = _plan([60.0] * 20, cpus=8, mem=16.0, monkeypatch=monkeypatch)
    assert plan.workers == 8  # CPU-bound
    plan, _ = _plan([60.0] * 20, engine="whisper", model="medium", cpus=32, mem=16.0, monkeypatch=monkeypatch)
    assert plan.workers == 2  # 0.8 * 16 GB / 5 GB per medium model
    plan, _ = _plan([60.0] * 3, cpus=8, monkeypatch=monkeypatch)
    assert plan.workers == 3  # no more workers than units of work
    plan, _ = _plan([60.0] * 20, jobs=2, monkeypatch=monkeypatch)
    assert plan.workers == 2 and "--jobs 2 requested" in plan.reasons


def test_whisper_workers_share_cores_without_oversubscription(monkeypatch):
    plan, _ = _plan([600.0] * 8, engine="whisper", model="base", cpus=8, mem=64.0, monkeypatch=monkeypatch)
    assert plan.workers * plan.torch_threads <= 8
    assert plan.torch_threads >= 1 and not plan.split  # splitting is opt-in for Whisper


def test_longest_work_first(monkeypatch):
    plan, _ = _plan([30.0, 300.0, 90.0], split=False, monkeypatch=monkeypatch)
    assert [u.duration for u in plan.units] == [300.0, 90.0, 30.0]


def test_long_file_is_split_at_pauses_when_workers_would_idle(monkeypatch):
    # 1200 s over 4 cores -> parts of ~150 s (targets 150, 300, ..., 1050); pauses
    # exist near 300, 600 and 900 only, elsewhere the cut is a hard cut.
    plan, _ = _plan([1200.0], cpus=4, pauses=[295.0, 610.0, 905.0], monkeypatch=monkeypatch)
    parts = sorted(plan.units, key=lambda u: u.start)
    assert len(parts) > plan.workers == 4  # more parts than workers: idle workers pick up the rest
    assert all(u.parts == len(parts) for u in parts)
    assert parts[0].start == 0.0 and parts[-1].end == 1200.0
    assert all(a.end == b.start for a, b in zip(parts, parts[1:]))  # contiguous, nothing lost
    starts = {round(p.start) for p in parts[1:]}
    assert {295, 610, 905} <= starts  # cuts with a pause nearby land on that pause
    assert not starts & {300, 600, 900}  # ... instead of on the hard target


def test_no_split_when_files_already_keep_workers_busy(monkeypatch):
    plan, _ = _plan([300.0] * 8, cpus=4, pauses=[100.0, 200.0], monkeypatch=monkeypatch)
    assert len(plan.units) == 8 and not plan.split


def test_cut_points_prefer_pauses_and_fall_back_to_hard_cuts():
    assert parallel.cut_points(600.0, 300.0, [290.0, 420.0]) == [290.0]
    assert parallel.cut_points(600.0, 300.0, []) == [300.0]  # no pause nearby: hard cut


def test_merge_shifts_segments_by_part_start():
    a = parallel.Unit(0, Path("x"), 0.0, 10.0, part=0, parts=2)
    b = parallel.Unit(0, Path("x"), 10.0, 25.0, part=1, parts=2)
    merged = parallel.merge([
        (b, {"text": "world", "segments": [{"start": 1.0, "end": 2.0, "text": "world"}], "language": "en", "duration": 15.0}),
        (a, {"text": "hello", "segments": [{"start": 0.5, "end": 1.5, "text": "hello"}], "language": "en", "duration": 10.0}),
    ])
    assert merged["text"] == "hello world"
    assert [(s["start"], s["end"]) for s in merged["segments"]] == [(0.5, 1.5), (11.0, 12.0)]
    assert merged["duration"] == 25.0


class _FakeEngine:
    model_name = "fake"

    def transcribe(self, path, language=None):
        if "bad" in str(path):
            raise asr.EngineError("cannot read")
        return {"text": f"transcript of {Path(path).stem}", "language": "en", "duration": 5.0,
                "segments": [{"start": 0.0, "end": 5.0, "text": f"transcript of {Path(path).stem}"}]}


def test_run_calls_back_once_per_file_and_isolates_failures(monkeypatch):
    monkeypatch.setattr(asr, "load", lambda engine, model=None: _FakeEngine())
    files = [Path("a.wav"), Path("bad.wav"), Path("c.wav")]
    plan = parallel.make_plan(files, "pocketsphinx", None, resources=(4, 8.0), durations=[5.0, 5.0, 5.0])
    done, logs = {}, []
    outcome = parallel.run(plan, files, "pocketsphinx", None, "en", lambda i, r, s: done.__setitem__(i, r),
                           log=logs.append, executor="thread")
    assert sorted(done) == [0, 2] and sorted(outcome.ok) == [0, 2]
    assert list(outcome.failed) == [1] and "cannot read" in outcome.failed[1]
    assert done[2]["text"] == "transcript of c"
    assert any("ETA" in line for line in logs)
    assert "2 file(s) done, 1 failed" in parallel.summary(outcome, plan)


def test_cli_uses_the_plan_and_writes_every_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(asr, "load", lambda engine, model=None: _FakeEngine())
    monkeypatch.setattr(asr, "status", lambda: {"whisper": (False, "-"), "pocketsphinx": (True, "5.1.1")})
    monkeypatch.setattr(cli.parallel, "run", functools.partial(cli.parallel.run, executor="thread"))
    monkeypatch.setattr(cli.parallel, "system_resources", lambda: (4, 8.0))
    monkeypatch.setattr(cli.parallel, "probe_duration", lambda p: 5.0)
    files = []
    for name in ("one", "two", "three"):
        f = tmp_path / f"{name}.wav"
        f.write_bytes(b"\0" * 100)
        files.append(str(f))
    assert cli.main(["transcribe", *files, "--engine", "pocketsphinx", "--out", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert "Plan: 3 file(s)" in out and "3 worker process(es)" in out and "Parallel run: 3 file(s) done" in out
    for i, name in enumerate(("one", "two", "three")):
        meta = json.loads((tmp_path / "o" / f"run-{i}" / "transcript.json").read_text())["meta"]
        assert meta["source"].endswith(f"{name}.wav") and meta["engine"] == "pocketsphinx"


def test_jobs_one_keeps_the_sequential_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.parallel, "run", lambda *a, **k: pytest.fail("parallel path used"))
    monkeypatch.setattr(asr, "load", lambda engine, model=None: _FakeEngine())
    monkeypatch.setattr(asr, "status", lambda: {"whisper": (False, "-"), "pocketsphinx": (True, "5.1.1")})
    monkeypatch.setattr(cli, "_MODEL_CACHE", {})
    f = tmp_path / "a.wav"
    f.write_bytes(b"\0" * 100)
    assert cli.main(["transcribe", str(f), str(f), "--engine", "pocketsphinx", "--jobs", "1",
                     "--out", str(tmp_path / "o")]) == 0


def test_invalid_input_is_rejected_before_any_output_folder_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(asr, "status", lambda: {"whisper": (False, "-"), "pocketsphinx": (True, "5.1.1")})
    monkeypatch.chdir(tmp_path)  # default output folder would be created here
    f = tmp_path / "a.wav"
    f.write_bytes(b"\0" * 100)
    with pytest.raises(SystemExit) as exc:
        cli.main(["transcribe", str(f), "--engine", "pocketsphinx", "--jobs", "zero"])
    assert "--jobs" in str(exc.value.code)
    with pytest.raises(SystemExit) as exc:
        cli.main(["transcribe", str(tmp_path / "missing.wav"), "--engine", "pocketsphinx"])
    assert "Cannot find audio file" in str(exc.value.code)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.wav"]  # no empty audio-brief-* folder


@pytest.mark.skipif(importlib.util.find_spec("pocketsphinx") is None or not shutil.which("ffmpeg"),
                    reason="needs pocketsphinx and ffmpeg")
def test_real_worker_processes(tmp_path):
    files = []
    for name in ("first", "second"):
        dest = tmp_path / f"{name}.wav"
        shutil.copy(WAV, dest)
        files.append(dest)
    plan = parallel.make_plan(files, "pocketsphinx", None, jobs=2)
    results = {}
    outcome = parallel.run(plan, files, "pocketsphinx", None, "en", lambda i, r, s: results.__setitem__(i, r),
                           log=lambda m: None)
    assert not outcome.failed and sorted(results) == [0, 1]
    assert results[0]["text"] == results[1]["text"] != ""  # same audio, same words, separate processes
