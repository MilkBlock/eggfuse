#!/usr/bin/env python3
"""Validate saved throughput samples and retain all observations and costs."""
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name("measure.py")))
read, sha = helpers["read"], helpers["sha"]


def collect(root, output):
    source = read(root / "samples.json")
    assert source.get("finished_at_utc")
    acceptance = read(root.parent / "semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == source["cases"]["sum"]["references"]["current"]["state_sha256"]
    result = {k: source[k] for k in (
        "scope", "candidate_commit", "checkpoint_commit", "historical_fast_commit",
        "started_at_utc", "finished_at_utc", "runtime_sha256", "proof_sha256", "limits")}
    result["raw_samples_sha256"] = sha(root / "samples.json")
    result["candidate_native_sum_acceptance_sha256"] = sha(root.parent / "semantic-acceptance.json")
    result["cases"] = {}
    fields = (*helpers["ACTUAL"], "bindings", "single_writes", "idle_scheduled_runs")
    costs = ("entry_publication_writes", "publication_slot_probes", "staged_root_records")
    for case, data in source["cases"].items():
        record = result["cases"][case] = {k: data[k] for k in
            ("repeat", "warmups", "program_sha256", "references", "comparisons", "execution_order")}
        record["lanes"] = {}
        control = data["lanes"]["checkpoint"]["samples"][0]
        for name, lane in data["lanes"].items():
            assert len(lane["samples"]) == data["repeat"] and len(lane["warmups"]) == 1
            assert [s["iteration"] for s in lane["samples"]] == list(range(data["repeat"]))
            expected = data["references"]["fast" if name == "fast" else "current"]
            first = lane["warmups"][0]
            for sample in lane["samples"] + lane["warmups"]:
                for key in ("state_sha256", "logical_schedule_sha256"):
                    assert sample[key] == expected[key]
                assert sample["schedule_sha256"] == first["schedule_sha256"]
                assert sample["stats"] == first["stats"]
                assert sample["allocations"] is None and sample["setup_allocations"] is None
                if name != "fast":
                    assert all(sample["stats"][k] == control["stats"][k] for k in helpers["ACTUAL"])
                if name != "fast":
                    a = sample["absorption"]
                    assert a["enabled"] and not any(a["stats"]["pending"])
                    assert sample["stats"]["bindings"] == control["stats"]["bindings"]
                    assert sample["stats"]["single_writes"] == control["stats"]["single_writes"]
                    assert a["stats"]["matches_absorbed"] == control["absorption"]["stats"]["matches_absorbed"]
                else:
                    assert sample["schedule_sha256"] == expected["schedule_sha256"]
            worker = first.get("query_workers") or {}
            absorption = first["absorption"]
            if absorption:
                absorption = {**absorption, "stats": {k: v for k, v in absorption["stats"].items() if k != "pending"},
                              "pending_all_drained": True}
            timing_fields = ("iteration", "inference_seconds", "process_wall_seconds", "process_user_seconds", "process_system_seconds")
            record["lanes"][name] = {
                "timing": lane["timing"], "phases": lane["phases"], "args": lane["args"],
                "queries": first["key_lookup_calls"],
                "execution_counts": {k: first["stats"][k] for k in fields},
                "entry_work": {k: first["entry_schedule_stats"].get(k) for k in costs},
                "absorption": absorption, "executed_schedule_sha256": first["schedule_sha256"],
                "sieve":first["sieve"], "publication":first["publication"],
                "query_workers": {"enabled": worker.get("enabled"),
                    "counts": {k: worker.get("stats", {}).get(k)
                               for k in ("entries", "coordinator_entries", "worker_entries")}},
                "samples": [{k: s[k] for k in timing_fields} for s in lane["samples"]],
                "warmups": [{k: s[k] for k in timing_fields} for s in lane["warmups"]],
            }
    helpers["process"]["save"](output, result)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("run without Python -O")
    collect(*map(Path, sys.argv[1:]))
