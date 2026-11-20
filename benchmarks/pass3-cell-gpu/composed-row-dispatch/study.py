"""Transfer the fixed and trained row dispatchers onto the composed resident CPU path."""
import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from certify import lower_shared_one

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("composed_cpu", HERE.parent / "composed-cpu/study.py")
composed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composed)
source = composed.base


def settings(req, args):
    baseline = composed.choices(req, args)["combined-lazy"]
    rows = dict(baseline["rows"])
    del rows["action"]
    archive = json.loads((HERE.parent / "adaptive-row-policy/checkpoints.json").read_bytes())
    model = archive[f"{args.seed}-policy-gradient-8-8.json"]
    assert model["params"] == 120 and model["max_rows"] == 8
    policy = dict(policy=model["weights"], max_rows=8, workers=8)
    compiled = lower_shared_one(policy, json.loads(Path(req["single_config"]).read_bytes()))
    assert compiled == dict(action=4, max_rows=1, workers=1)
    actions = {
        "off": compiled,
        "direct-1": dict(action=0, max_rows=1, workers=1),
        "direct-8": dict(action=3, max_rows=8, workers=8),
        "serial-8": dict(action=7, max_rows=8, workers=1),
        "shared-8": dict(action=7, max_rows=8, workers=8),
        "policy-8": policy,
    }
    return {name: dict(baseline, rows={**rows, **action}) for name, action in actions.items()}


def observe(arm, execution, result, previous):
    emitter = execution["single"]["adaptive_rows"]
    result["issuer"] = {k: emitter["stats"][k] for k in
                        ("calls", "addressed", "source_headers", "evaluations", "emitted",
                         "invocations", "peak_workers", "real_parallel_calls")}
    result["score_digest"] = emitter["decision_digest"]
    assert result["issuer"]["emitted"] > 0
    if arm != "off":
        for name in ("raw", "multi", "commits", "physical", "children", "cells", "score_digest"):
            assert result[name] == previous["off"][name], (arm, name)


def phases(args):
    args.out.mkdir(parents=True, exist_ok=False)
    report = {}
    for name in args.cases:
        program, plan, req = source.common.config(args, name)
        arms = settings(req, args)
        with source.base.session(args.exp / "compact-vanilla-20261121/vanilla", program) as vanilla:
            gold = vanilla({})
        with source.base.session(args.native, program, plan) as infer:
            for arm, cfg in arms.items():
                times = []
                for trial in range(args.repeats + 1):
                    start = perf_counter_ns()
                    v = infer(dict(cfg, rows=dict(cfg["rows"], profile=True)))
                    roundtrip = (perf_counter_ns() - start) / 1e6
                    assert v["state_sha"] == gold["state_sha"] and v["runs"] == gold["runs"]
                    if trial:
                        parts = [n / 1e6 for n in v["single"]["adaptive_rows"]["phase_ns"]]
                        times.append([*parts, v["ms"], roundtrip])
                report.setdefault(name, {})[arm] = dict(samples=times, ms=list(map(median, zip(*times))))
        (args.out / "phases.json").write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("exp", "native", "out"):
        p.add_argument(key, type=Path)
    p.add_argument("--cases", nargs="+", default=["sum-bits", "conjugate-gradient", "3mm"])
    p.add_argument("--seed", type=int, choices=(1703, 1709), default=1703)
    p.add_argument("--repeats", type=int, default=4)
    p.add_argument("--phases", action="store_true")
    args = p.parse_args()
    if args.phases:
        phases(args)
    else:
        source.study(args, settings, observe, None)
