#!/usr/bin/env python3
"""Collect frozen allocation/semantic evidence without executing workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, output):
    acceptance = read(root / "semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root / "sum/state.json")
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch",
              "logical_matches", "executed_bindings", "changed")
    result = {"baseline_commit": "4ebea808", "scope": "standalone Cell CPU; allocation diagnostics, not throughput",
              "limits": "One allocator-instrumented run per lane and case, four workers. Raytrace covers 1280 Runs; no full Raytrace/native or general sparsity proof.",
              "prefix_sha256": [sha(root / name) for name in ("before-prefix", "prefix")],
              "sum_acceptance_sha256": sha(root / "semantic-acceptance.json"), "cases": {}}
    for case in ("sum", "ray1280"):
        before, after = root / (case + "-before"), root / case
        a, b = [read(p / "report.json") for p in (before, after)]
        assert read(before / "state.json") == read(after / "state.json")
        assert [[s[k] for k in fields] for s in a["steps"]] == [[s[k] for k in fields] for s in b["steps"]]
        for k in ("program_sha256", "prefix_configuration", "stats", "key_lookup_calls"):
            assert a[k] == b[k], k
        x, y = [r["entry_schedule"]["stats"] for r in (a, b)]
        assert all(x[k] == y[k] for k in x if k != "parameter_packets_reused")
        assert y["parameter_packets_reused"] == 0
        assert y["row_reuse_checks"] == y["row_reuses"] + y["row_reuse_shared"]
        assert y["row_reuses"] > 0
        for k in ("anchor_publications", "completed_steps", "history_capture_reads", "resumed_steps"):
            assert a["stage_spine"]["stats"][k] == b["stage_spine"]["stats"][k]
        alloc = {k: [a["allocations"][k], b["allocations"][k]]
                 for k in ("alloc_calls", "realloc_calls", "requested_bytes")}
        # In these frozen samples the allocator saving reconciles exactly with
        # the reused outer Rc<Row>. A different worker assignment may also
        # change scratch growth; investigate instead of attributing it here.
        assert alloc["alloc_calls"][0] - alloc["alloc_calls"][1] == y["row_reuses"]
        assert alloc["realloc_calls"][0] == alloc["realloc_calls"][1]
        result["cases"][case] = {
            "configuration": b["prefix_configuration"], "runs": len(b["steps"]),
            "exact_final_graph_and_run_records": True, "actual_effect_counts_unchanged": True,
            "queries": b["key_lookup_calls"],
            "row_work": {k: y[k] for k in ("row_decodes", "private_row_reads", "row_reuse_checks", "row_reuses", "row_reuse_shared")},
            "legacy_parameter_reuse_counter": [x["parameter_packets_reused"], y["parameter_packets_reused"]],
            "allocations": alloc,
            "entry_publications": y["entry_publication_writes"],
            "program_sha256": b["program_sha256"],
            "report_sha256": [sha(p / "report.json") for p in (before, after)],
            "state_sha256": [sha(p / "state.json") for p in (before, after)],
        }
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(*map(Path, sys.argv[1:]))
