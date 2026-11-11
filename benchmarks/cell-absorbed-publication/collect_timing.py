#!/usr/bin/env python3
"""Keep checkpoint samples and uncertainty without launching another workload."""
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name("measure.py")))
read, sha = helpers["read"], helpers["sha"]


def collect(root, output):
    source = read(root / "samples.json")
    previous = read(Path(__file__).resolve().parent.parent / "cell-publication-windows/results.json")
    assert source.get("finished_at_utc")
    result = {k: source[k] for k in (
        "scope", "candidate_commit", "checkpoint_commit", "historical_fast_commit",
        "started_at_utc", "finished_at_utc", "runtime_sha256", "proof_sha256", "limits")}
    result["raw_samples_sha256"] = sha(root / "samples.json")
    result["cases"] = {}
    fields = ("bindings", "function_updates", "unions", "logical_facts_created", "single_writes")
    costs = ("entry_publication_writes", "staged_root_records", "staged_root_checks", "staged_root_winners")
    for case, data in source["cases"].items():
        record = result["cases"][case] = {k: data[k] for k in
            ("repeat", "warmups", "program_sha256", "references", "comparisons")}
        record["lanes"] = {}
        control = data["lanes"]["checkpoint"]["samples"][0]
        for name, lane in data["lanes"].items():
            assert len(lane["samples"]) == data["repeat"] and len(lane["warmups"]) == 1
            assert [s["iteration"] for s in lane["samples"]] == list(range(data["repeat"]))
            expected = data["references"]["fast" if name == "fast" else "current"]
            for sample in lane["samples"] + lane["warmups"]:
                assert all(sample[k] == v for k, v in expected.items())
                assert sample["allocations"] is None
                if name.startswith("current"):
                    # Worker queries already differed at the prior checkpoint;
                    # compare work under the same worker configuration.
                    assert sample["key_lookup_calls"] == previous["cases"][case]["lanes"][name]["queries"]
                    assert all(sample["stats"][k] == control["stats"][k] for k in fields)
                    assert sample["stage_spine_stats"]["absorbed_root_completions"] > 0
            first = lane["samples"][0]
            worker = first.get("query_workers") or {}
            record["lanes"][name] = {
                "timing": lane["timing"], "phases": lane["phases"], "args": lane["args"],
                "queries": first["key_lookup_calls"],
                "execution_counts": {k: first["stats"][k] for k in fields},
                "entry_work": {k: first["entry_schedule_stats"].get(k) for k in costs},
                "absorbed_roots": first["stage_spine_stats"].get("absorbed_root_completions"),
                "query_workers": {"enabled": worker.get("enabled"),
                    "counts": {k: worker.get("stats", {}).get(k)
                               for k in ("entries", "coordinator_entries", "worker_entries")}},
                "samples": [{k: s[k] for k in ("iteration", "inference_seconds", "process_wall_seconds")}
                            for s in lane["samples"]],
            }
    helpers["process"]["save"](output, result)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(*map(Path, sys.argv[1:]))
