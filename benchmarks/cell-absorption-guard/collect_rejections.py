#!/usr/bin/env python3
"""Recheck saved direct-rejection results; does not execute or time workloads."""
import gzip
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as f:
        return json.load(f)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def counts(stats):
    # Diagnostics already record clocks; they are not performance observations.
    return {k:v for k,v in stats.items() if not k.endswith("_seconds")}


def steps(report):
    keys = ("ordinal", "epoch", "ruleset", "path", "iterations", "logical_matches",
            "executed_bindings", "local_bindings", "changed", "live_cells")
    return [[s[k] for k in keys] for s in report["steps"]]


def collect(root, output):
    before = root.parent / "cell-absorption-guard"
    acceptance = read(root / "semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root / "sum/state.json")
    result = {"baseline_commit":"91cfda31", "scope":"standalone Cell CPU; no timing or sparsity theorem",
              "cases":{}, "native_sum_acceptance_sha256":sha(root / "semantic-acceptance.json")}
    for case in ("sum", "ray1280", "ray-full"):
        a, b = (read(p / case / "report.json") for p in (before, root))
        assert sha(before / case / "state.json") == sha(root / case / "state.json"), case
        for key in ("program_sha256", "prefix_configuration", "stats", "key_lookup_calls"):
            assert a[key] == b[key], (case, key)
        assert steps(a) == steps(b), case
        for key in ("stage_spine", "entry_schedule"):
            assert counts(a[key]["stats"]) == counts(b[key]["stats"]), (case, key)
        x, y = (r["neighbor_context"]["absorption"] for r in (a, b))
        assert x["condition_bytes_per_neighborhood"] == y["condition_bytes_per_neighborhood"] == 32
        for key in ("checks", "groups_absorbed", "matches_absorbed", "reused_bounds", "pending"):
            assert x["stats"][key] == y["stats"][key], (case, key)
        assert not any(y["stats"]["pending"])
        assert y["stats"]["output_probes"] <= x["stats"]["output_probes"]
        probes = y["stats"]["output_probes"]
        direct = y["stats"]["rejection_reads"]
        if case == "ray-full":
            assert probes + direct < x["stats"]["output_probes"]
            assert y["stats"]["rejection_hits"] > 0
        allocations = {k:[a["allocations"][k],b["allocations"][k]]
                       for k in ("alloc_calls", "realloc_calls", "requested_bytes")}
        assert allocations["alloc_calls"][0] == allocations["alloc_calls"][1], (case, allocations)
        # Worker assignment can grow a different scratch frame. Keep those
        # measured reallocations/bytes rather than asserting them away.
        scratch = {k:[a["query_workers"]["stats"][k],b["query_workers"]["stats"][k]]
                   for k in ("frame_allocations", "worker_frame_capacity_bytes")}
        assert (allocations["realloc_calls"][1]-allocations["realloc_calls"][0]
                == scratch["frame_allocations"][1]-scratch["frame_allocations"][0]), (case, allocations, scratch)
        result["cases"][case] = {"runs":len(b["steps"]),
            "exact_state_work_and_ordered_runs":True, "state_sha256":sha(root / case / "state.json"),
            "condition_bytes_per_neighborhood":32,
            "conditions_before":{k:v for k,v in x["stats"].items() if k != "pending"},
            "conditions_after":{k:v for k,v in y["stats"].items() if k != "pending"},
            "output_hash_probes_removed":x["stats"]["output_probes"]-probes,
            "total_output_observations":[x["stats"]["output_probes"], probes+direct],
            "allocations":allocations,
            "worker_scratch":scratch,
            "reports_sha256":[sha(p / case / "report.json") for p in (before, root)]}
    # All selected source captures must be identical, including match ordinals,
    # actual effects, visibility and source provenance. No exclusions are added.
    windows = sorted((root / "windows").glob("run-*.json.gz"))
    assert len(windows) == 14
    assert read(root/"windows/checks.json")["state_sha256"] == read(before/"windows/checks.json")["state_sha256"]
    assert steps(read(root/"windows/report.json")) == steps(read(before/"windows/report.json"))
    for path in windows:
        a,b = read(before / "windows" / path.name),read(path)
        # Only the Run's measured clocks differ; all captured source evidence
        # and every other step field remain authoritative.
        assert a["step"]["phases"].keys() == b["step"]["phases"].keys()
        for snapshot in (a,b):
            snapshot["step"].pop("elapsed_seconds")
            snapshot["step"].pop("phases")
        assert a == b, path.name
    result["source_windows"] = {"count":len(windows), "exact_captures":True,
        "artifacts_sha256":{p.name:sha(p) for p in windows}}
    repeat = read(root/"ray1280-repeat/report.json")
    first = read(root/"ray1280/report.json")
    assert repeat["stats"] == first["stats"] and steps(repeat) == steps(first)
    assert sha(root/"ray1280-repeat/state.json") == sha(root/"ray1280/state.json")
    result["prefix_repeat"] = {"exact_state_work_and_runs":True,
        "allocations":{k:repeat["allocations"][k] for k in ("alloc_calls","realloc_calls","requested_bytes")},
        "worker_scratch":{k:repeat["query_workers"]["stats"][k] for k in ("frame_allocations","worker_frame_capacity_bytes")},
        "report_sha256":sha(root/"ray1280-repeat/report.json")}
    result["binaries"] = {name:sha(root/name) for name in ("prefix", "observer")}
    output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__: raise SystemExit("run without Python -O")
    collect(*map(Path,sys.argv[1:]))
