#!/usr/bin/env python3
"""Measure the five-commit checkpoint against frozen, already validated states."""
import datetime
import os
from pathlib import Path
import random
import runpy
import sys

HERE = Path(__file__).resolve().parent
previous = runpy.run_path(str(HERE.parent / "cell-publication-windows/measure.py"))
read, sha, stamp = (previous[k] for k in ("read", "sha", "stamp"))
base, process, summary = (previous[k] for k in ("base", "process", "summary"))


def measure(root, output, current, checkpoint, fastest):
    saved = read(HERE.parent / "cell-publication-windows/results.json")
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
        "scope": "standalone Cell CPU; cumulative checkpoint, not native egglog",
        "candidate_commit": "9560f11e", "checkpoint_commit": "4cfd0f7e",
        "historical_fast_commit": saved["historical_fast_commit"],
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "proof_sha256": saved["proof_sha256"],
        "runtime_sha256": {k: sha(v) for k, v in
            (("fast", fastest), ("checkpoint", checkpoint), ("current", current))},
        "limits": "Cumulative changes since 4cfd0f7e, not isolated attribution. Every candidate sample must reproduce its validated checkpoint's exact state and ordered Runs. Relative Raytrace source-choice contract, not independent native proof. No profiling or allocation instrumentation.",
        "cases": {},
    }
    os.environ.pop("CELL_CPU_PROFILE", None)
    os.environ.pop("CELL_CPU_PROGRESS", None)
    rng = random.Random(20261111)
    flags = ["--repair-ports", "--entry-publications"]
    definitions = {
        "fast": (fastest, flags, "fast"),
        "checkpoint": (checkpoint, flags, "current"),
        "current": (current, flags, "current"),
        "current4": (current, flags + ["--query-workers", "4", "--query-grain", "64"], "current"),
    }
    for case, repeats in (("sum", 7), ("ray", 5)):
        program = root / f"{case}-program.json"
        assert sha(program) == saved["cases"][case]["program_sha256"]
        program_id = read(program)["sha256"]
        assert all(read(root / f"{case}-{lane}/report.json")["program_sha256"] == program_id
                   for lane in ("fast", "current"))
        target = output / case
        target.mkdir()
        references = {lane: stamp(root / f"{case}-{lane}") for lane in ("fast", "current")}
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
                assert all(sample[k] == v for k, v in references[reference].items()), (case, lane, "unproved state/Run deviation")
                assert sample.get("allocations") is None
                if lane.startswith("current"):
                    assert sample["stage_spine_stats"]["absorbed_root_completions"] > 0
                worker = sample.get("query_workers") or {}
                if worker.get("enabled"):
                    c = worker["stats"]
                    assert c["entries"] == c["coordinator_entries"] + sum(c["worker_entries"])
                sample["iteration"] = iteration
                record["lanes"][lane]["warmups" if iteration < 0 else "samples"].append(sample)
                process["save"](output / "samples.json", result)
        for lane in record["lanes"].values():
            rows = lane["samples"]
            lane["timing"] = {k: summary["distribution"]([r[k] for r in rows])
                for k in ("inference_seconds", "process_wall_seconds")}
            lane["phases"] = {k: summary["distribution"]([r["phases"][k] for r in rows])
                for k in rows[0]["phases"]}
        record["comparisons"] = {}
        for reference, candidate in (("fast", "current"), ("checkpoint", "current"),
                                      ("checkpoint", "current4"), ("current", "current4")):
            a, b = [record["lanes"][n]["samples"] for n in (reference, candidate)]
            record["comparisons"][candidate + "_over_" + reference] = {
                k: summary["paired_ratio"]([r[k] for r in a], [r[k] for r in b])
                for k in ("inference_seconds", "process_wall_seconds")}
    result["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    process["save"](output / "samples.json", result)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    measure(*[Path(x).resolve() for x in sys.argv[1:]])
