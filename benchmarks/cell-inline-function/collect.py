#!/usr/bin/env python3
"""Check saved Cell output-storage runs; launch no workload or speed test."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, output):
    baseline = root.parent / "cell-prefix-configuration"
    acceptance = read(root / "semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root / "sum/state.json")
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch",
              "logical_matches", "executed_bindings", "changed")
    retained = ("completed_steps", "anchor_publications", "history_capture_reads",
                "history_slots_written", "history_allocations", "cell_output_receipts",
                "cell_output_checks", "cell_output_deliveries", "receipt_redirects",
                "resumed_steps", "cell_output_spans", "fragment_deliveries")
    removed = ("effect_output_copies", "cell_output_slots", "cell_output_slot_reads")
    result = {"baseline_commit": "b47330c8", "scope": "standalone Cell CPU; bounded work counts, not throughput",
              "limits": "Raytrace covers the first 1280 Runs only; exact relative states and Run records, not independent native Raytrace proof or sparsity theorem.",
              "cases": {}, "sum_acceptance_sha256": sha(root / "semantic-acceptance.json"),
              "runtime_sha256": sha(root / "runtime"), "prefix_sha256": sha(root / "prefix")}
    for case in ("sum", "ray1280"):
        before, after = baseline / case, root / case
        a, b = [read(p / "report.json") for p in (before, after)]
        assert read(before / "state.json") == read(after / "state.json")
        assert [[s[k] for k in fields] for s in a["steps"]] == [[s[k] for k in fields] for s in b["steps"]]
        for k in ("program_sha256", "prefix_configuration", "stats", "key_lookup_calls"):
            assert a[k] == b[k], k
        assert a["entry_schedule"]["stats"] == b["entry_schedule"]["stats"]
        assert a["stage_spine"]["completion_record_bytes"] == b["stage_spine"]["completion_record_bytes"]
        x, y = [r["stage_spine"]["stats"] for r in (a, b)]
        assert all(x[k] == y[k] for k in retained)
        n = y["inline_function_receipts"]
        assert n > 0 and n == y["inline_function_reads"]
        assert all(x[k] - y[k] == n for k in removed)
        result["cases"][case] = {
            "configuration": b["prefix_configuration"], "runs": len(b["steps"]),
            "exact_final_graph_and_run_records": True, "actual_effect_counts_unchanged": True,
            "queries": b["key_lookup_calls"], "entry_maintenance_unchanged": True,
            "inline_function_receipts": n, "inline_function_reads": y["inline_function_reads"],
            "removed_arena_work": {k: [x[k], y[k]] for k in removed},
            "retained_work": {k: y[k] for k in retained},
            "peak_output_slots": [x["peak_cell_output_slots"], y["peak_cell_output_slots"]],
            "completion_record_bytes": b["stage_spine"]["completion_record_bytes"],
            "program_sha256": b["program_sha256"],
            "report_sha256": [sha(p / "report.json") for p in (before, after)],
            "state_sha256": [sha(p / "state.json") for p in (before, after)],
        }
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(*map(Path, sys.argv[1:]))
