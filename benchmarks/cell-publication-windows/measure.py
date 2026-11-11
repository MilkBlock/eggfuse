#!/usr/bin/env python3
"""Interleave frozen processes after the separate saved-state choice proofs."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import sys

HERE = Path(__file__).resolve().parent
base = runpy.run_path(str(HERE.parent / "witness-prefix/measure.py"))
base["GROUPS"]["query_workers"] = ("query_workers",)
process = runpy.run_path(str(HERE.parent / "raytrace-parallel/measure.py"))
summary = runpy.run_path(str(HERE.parent / "raytrace-parallel/collect.py"))
FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return process["sha"](p)


def stamp(directory):
    r = read(directory / "report.json")
    return {"state_sha256": sha(directory / "state.json"), "schedule_sha256": hashlib.sha256(
        json.dumps([[s[k] for k in FIELDS] for s in r["steps"]], separators=(",", ":")).encode()).hexdigest()}


def measure(root, output, current, fastest):
    acceptance = read(root / "sum-acceptance.json")
    assert acceptance["status"] == "pass"
    for lane, key in (("fast", "cpu_legacy"), ("current", "cpu_values")):
        assert acceptance["input_sha256"][key] == sha(root / f"sum-{lane}/state.json")
    proof = read(root / "ray-window-acceptance.json")
    assert proof["status"] == "pass"
    for lane in ("fast", "current"):
        assert proof["windows"][lane]["final_state_sha256"] == sha(root / f"ray-{lane}/state.json")
        assert proof["windows"][lane]["report_sha256"] == sha(root / f"ray-{lane}/report.json")
    output.mkdir()
    result = {"scope": "standalone Cell CPU; frozen compatible input per case; not native egglog",
              "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "proof_sha256": {name: sha(root / name) for name in ("sum-acceptance.json", "ray-window-acceptance.json")},
              "runtime_sha256": {"fast": sha(fastest), "current": sha(current)},
              "limits": "Relative Raytrace source-window contract; no independent native Raytrace proof. No profile or allocation instrumentation. Samples interleaved within each workload.",
              "cases": {}}
    os.environ.pop("CELL_CPU_PROFILE", None)
    os.environ.pop("CELL_CPU_PROGRESS", None)
    rng = random.Random(20261111)
    flags = ["--repair-ports", "--entry-publications"]
    for case, repeats in (("sum", 7), ("ray", 5)):
        program_id = read(root / f"{case}-program.json")["sha256"]
        assert all(read(root / f"{case}-{lane}/report.json")["program_sha256"] == program_id
                   for lane in ("fast", "current"))
        target = output / case
        target.mkdir()
        references = {lane: stamp(root / f"{case}-{lane}") for lane in ("fast", "current")}
        definitions = {"fast": (fastest, flags, "fast"), "current": (current, flags, "current"),
                       "current4": (current, flags + ["--query-workers", "4", "--query-grain", "64"], "current")}
        record = result["cases"][case] = {"repeat": repeats, "warmups": 1, "references": references,
            "program_sha256": sha(root / f"{case}-program.json"), "execution_order": [],
            "lanes": {label: {"args": args, "samples": [], "warmups": []} for label, (_, args, _) in definitions.items()}}
        for iteration in range(-1, repeats):
            order = list(definitions)
            rng.shuffle(order)
            record["execution_order"].append({"iteration": iteration, "lanes": order})
            for lane in order:
                binary, args, reference = definitions[lane]
                directory = target / f"{iteration + 1:04d}-{list(definitions).index(lane):04d}"
                spec = {"lanes": {lane: {"runtime": str(binary), "program": str(root / f"{case}-program.json"), "args": args}}}
                base["measure"](spec, directory, 1, 0, 90)
                sample = read(directory / "samples.json")["lanes"][lane]["samples"][0]
                assert all(sample[k] == v for k, v in references[reference].items()), (case, lane, "unproved state/Run deviation")
                assert sample.get("allocations") is None
                worker = sample.get("query_workers") or {}
                if worker.get("enabled"):
                    c = worker["stats"]
                    assert c["entries"] == c["coordinator_entries"] + sum(c["worker_entries"])
                sample["iteration"] = iteration
                record["lanes"][lane]["warmups" if iteration < 0 else "samples"].append(sample)
                process["save"](output / "samples.json", result)
        for lane in record["lanes"].values():
            rows = lane["samples"]
            lane["timing"] = {k: summary["distribution"]([r[k] for r in rows]) for k in ("inference_seconds", "process_wall_seconds")}
            lane["phases"] = {k: summary["distribution"]([r["phases"][k] for r in rows]) for k in rows[0]["phases"]}
        record["comparisons"] = {}
        for reference, candidate in (("fast", "current"), ("fast", "current4"), ("current", "current4")):
            a, b = [record["lanes"][n]["samples"] for n in (reference, candidate)]
            record["comparisons"][candidate + "_over_" + reference] = {k: summary["paired_ratio"]([r[k] for r in a], [r[k] for r in b])
                for k in ("inference_seconds", "process_wall_seconds")}
    result["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    process["save"](output / "samples.json", result)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    measure(*[Path(x).resolve() for x in sys.argv[1:]])
