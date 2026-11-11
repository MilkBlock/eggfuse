#!/usr/bin/env python3
"""Time frozen normal binaries; compare the maintenance checkpoint and optional reverse selection."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import sys

HERE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(HERE.parent / "cell-publication-windows/measure.py"))
read, sha, stamp = (helpers[k] for k in ("read", "sha", "stamp"))
base, process, summary = (helpers[k] for k in ("base", "process", "summary"))
LOGICAL = tuple(k for k in helpers["FIELDS"] if k != "executed_bindings")
ACTUAL = ("constructor_requests", "function_updates", "unions", "logical_facts_created")
original_groups = base["extra_groups"]


def logical_signature(report):
    rows = [[s[k] for k in LOGICAL] for s in report["steps"]]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def extra_groups(report):
    result = original_groups(report)
    result["logical_schedule_sha256"] = logical_signature(report)
    result["absorption"] = report.get("neighbor_context", {}).get("absorption")
    result["sieve"] = report.get("sieve")
    result["publication"] = report.get("publication")
    return result


base["measure"].__globals__["extra_groups"] = extra_groups


def measure(root, output, current, checkpoint, fastest, candidate_commit, plain=None):
    saved = read(HERE.parent / "cell-absorption-guard/timing.json")
    assert sha(checkpoint) == saved["runtime_sha256"]["current"]
    assert sha(fastest) == saved["runtime_sha256"]["fast"]
    acceptance = read(root / "sum-acceptance.json")
    assert acceptance["status"] == "pass"
    for lane, key in (("fast", "cpu_legacy"), ("current", "cpu_values")):
        assert acceptance["input_sha256"][key] == sha(root / f"sum-{lane}/state.json")
    proof = read(root / "ray-window-acceptance.json")
    assert proof["status"] == "pass"
    for lane in ("fast", "current"):
        assert proof["windows"][lane]["final_state_sha256"] == sha(root / f"ray-{lane}/state.json")
        assert proof["windows"][lane]["report_sha256"] == sha(root / f"ray-{lane}/report.json")
    for name, digest in saved["proof_sha256"].items():
        assert sha(root / name) == digest
    output.mkdir()
    result = {
        "scope": "standalone Cell CPU; normal release executables; not native egglog",
        "candidate_commit": candidate_commit, "checkpoint_commit": "2af82c27",
        "historical_fast_commit": "8fffff65",
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "proof_sha256": saved["proof_sha256"],
        "runtime_sha256": {k: sha(v) for k, v in
            (("fast", fastest), ("checkpoint", checkpoint), ("current", current))},
        "limits": "Current/checkpoint charges cumulative changes; same-binary reverse/current isolates optional Entry selection. All nonhistorical lanes enable absorption. Exact states and logical Run signatures required; per-lane executed Run signatures repeat exactly. Raytrace evidence remains relative, not independent native proof. No profiler or allocation instrumentation.",
        "cases": {},
    }
    os.environ.pop("CELL_CPU_PROFILE", None)
    os.environ.pop("CELL_CPU_PROGRESS", None)
    rng = random.Random(20261112)
    flags = ["--repair-ports", "--entry-publications"]
    definitions = {
        "fast": (fastest, flags, "fast"),
        "checkpoint": (checkpoint, flags + ["--cell-absorption"], "current"),
        "current": (current, flags + ["--cell-absorption"], "current"),
        "reverse": (current, flags + ["--cell-absorption", "--cell-entry-reverse"], "current"),
        "current4": (current, flags + ["--cell-absorption", "--query-workers", "4", "--query-grain", "64"], "current"),
    }
    if plain is not None:
        result["runtime_sha256"]["plain"] = sha(plain)
        result["limits"] += " Targeted follow-up: checkpoint, compiled-with-reverse-but-disabled current, and no-reverse-feature plain. Historical fast is an input-proof reference, not a measured lane in this follow-up."
        definitions = {"checkpoint":definitions["checkpoint"], "current":definitions["current"],
            "plain":(plain,flags+["--cell-absorption"],"current")}
    for case, repeats in (("sum", 7), ("ray", 5)):
        program = root / f"{case}-program.json"
        assert sha(program) == saved["cases"][case]["program_sha256"]
        program_id = read(program)["sha256"]
        reports = {lane: read(root / f"{case}-{lane}/report.json") for lane in ("fast", "current")}
        assert all(r["program_sha256"] == program_id for r in reports.values())
        target = output / case
        target.mkdir()
        references = {lane: {**stamp(root / f"{case}-{lane}"),
                            "logical_schedule_sha256": logical_signature(report)}
                      for lane, report in reports.items()}
        record = result["cases"][case] = {
            "repeat": repeats, "warmups": 1, "references": references,
            "program_sha256": sha(program), "execution_order": [],
            "lanes": {label: {"args": args, "samples": [], "warmups": []}
                      for label, (_, args, _) in definitions.items()},
        }
        for iteration in range(-1, repeats):
            order = list(definitions)
            rng.shuffle(order)
            record["execution_order"].append({"iteration": iteration, "lanes": order})
            for lane in order:
                binary, args, reference = definitions[lane]
                directory = target / f"{iteration + 1:04d}-{list(definitions).index(lane):04d}"
                spec = {"lanes": {lane: {"runtime": str(binary), "program": str(program), "args": args}}}
                base["measure"](spec, directory, 1, 0, 90)
                sample = read(directory / "samples.json")["lanes"][lane]["samples"][0]
                assert sample["allocations"] is None
                expected = references[reference]
                for key in ("state_sha256", "logical_schedule_sha256"):
                    assert sample[key] == expected[key], (case, lane, key)
                assert all(sample["stats"][k] == reports[reference]["stats"][k] for k in ACTUAL)
                if lane != "fast":
                    a = sample["absorption"]
                    assert a["enabled"] and a["stats"]["matches_absorbed"] > 0
                    assert not any(a["stats"]["pending"])
                    for key in ("bindings", "single_writes"):
                        assert reports[reference]["stats"][key] - sample["stats"][key] == a["stats"]["matches_absorbed"]
                else:
                    assert sample["schedule_sha256"] == expected["schedule_sha256"]
                lane_record = record["lanes"][lane]
                if lane_record["warmups"]:
                    first = lane_record["warmups"][0]
                    assert sample["schedule_sha256"] == first["schedule_sha256"]
                    assert sample["stats"] == first["stats"]
                    assert sample["absorption"] == first["absorption"]
                    assert sample["sieve"] == first["sieve"]
                    assert sample["publication"] == first["publication"]
                worker = sample.get("query_workers") or {}
                if worker.get("enabled"):
                    c = worker["stats"]
                    assert c["entries"] == c["coordinator_entries"] + sum(c["worker_entries"])
                sample["iteration"] = iteration
                lane_record["warmups" if iteration < 0 else "samples"].append(sample)
                process["save"](output / "samples.json", result)
        for lane in record["lanes"].values():
            rows = lane["samples"]
            lane["timing"] = {k: summary["distribution"]([r[k] for r in rows])
                for k in ("inference_seconds", "process_wall_seconds")}
            lane["phases"] = {k: summary["distribution"]([r["phases"][k] for r in rows])
                for k in rows[0]["phases"]}
        record["comparisons"] = {}
        pairs = (("checkpoint","current"),("checkpoint","plain"),("current","plain")) if plain is not None else (
            ("fast", "current"), ("fast", "reverse"), ("fast", "current4"),
            ("checkpoint", "current"), ("checkpoint", "reverse"), ("current", "reverse"), ("current", "current4"))
        for reference, candidate in pairs:
            a, b = [record["lanes"][n]["samples"] for n in (reference, candidate)]
            record["comparisons"][candidate + "_over_" + reference] = {
                k: summary["paired_ratio"]([r[k] for r in a], [r[k] for r in b])
                for k in ("inference_seconds", "process_wall_seconds")}
    result["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    process["save"](output / "samples.json", result)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("run without Python -O")
    measure(*[Path(x).resolve() for x in sys.argv[1:6]], sys.argv[6],
        Path(sys.argv[7]).resolve() if len(sys.argv)>7 else None)
