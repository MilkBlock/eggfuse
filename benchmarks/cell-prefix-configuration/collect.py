#!/usr/bin/env python3
"""Check saved diagnostic configurations; run no workload or timing campaign."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


RUN_FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch",
              "logical_matches", "executed_bindings", "changed")
EXECUTION_FIELDS = ("bindings", "constructor_requests", "logical_facts_created",
                 "function_updates", "unions", "single_writes", "transient_writes")
SPINE_FIELDS = ("completed_steps", "anchor_publications", "ripsat_completed",
                "history_capture_reads", "history_slots_written", "history_shared_slots",
                "history_allocations", "legacy_entry_writes", "output_registrations",
                "cell_output_receipts", "cell_output_registrations", "cell_output_slot_reads",
                "cell_output_slots", "cell_output_spans", "cell_output_span_seals",
                "cell_output_sealed_receipts", "fragment_deliveries")


def compare(before, after):
    a, b = [read(p / "report.json") for p in (before, after)]
    assert a["program_sha256"] == b["program_sha256"]
    assert read(before / "state.json") == read(after / "state.json")
    assert [[s[k] for k in RUN_FIELDS] for s in a["steps"]] == [
        [s[k] for k in RUN_FIELDS] for s in b["steps"]]
    assert all(a["stats"][k] == b["stats"][k] for k in EXECUTION_FIELDS)
    assert a["key_lookup_calls"] == b["key_lookup_calls"]
    assert all(a["stage_spine"]["stats"][k] == b["stage_spine"]["stats"][k]
               for k in ("completed_steps", "anchor_publications", "ripsat_completed"))
    return {"exact_final_graph": True, "ordered_run_records": True,
            "bindings_and_effect_counts": True, "queries_equal": True,
            "report_sha256": [sha(p / "report.json") for p in (before, after)]}


def collect(root, output):
    old = root.parent / "cell-attribute-locality"
    checks = {
        "sum_prefix_vs_main_cli": compare(old / "sum", root / "sum"),
        "ray_legacy_compatibility": compare(old / "ray1280", root / "ray1280-legacy"),
        "ray_configurations": compare(root / "ray1280-legacy", root / "ray1280"),
    }
    cases = {}
    for name in ("sum", "ray1280-legacy", "ray1280"):
        p = root / name
        r = read(p / "report.json")
        c = r["prefix_configuration"]
        enabled = name != "ray1280-legacy"
        assert c == {"backend": "canonical", "grain": 64, "workers": 4,
                     "requested_entry_publications": enabled,
                     "requested_repair_ports": enabled,
                     "requested_runs": 2000 if name == "sum" else 1280}
        assert r["repair_ports"]["enabled"] == enabled
        assert (r["stage_spine"]["node_entry_references"] > 0) == enabled
        cases[name] = {
            "configuration": c, "runs_completed": len(r["steps"]),
            "repair_ports_enabled": r["repair_ports"]["enabled"],
            "queries": r["key_lookup_calls"],
            "execution_counts": {k: r["stats"][k] for k in EXECUTION_FIELDS},
            "repaired_dependencies": r["stats"]["repaired_dependencies"],
            "entry_references": {k: r["stage_spine"][k] for k in
                                 ("node_entry_references", "legacy_entry_references")},
            "spine_work": {k: r["stage_spine"]["stats"][k] for k in SPINE_FIELDS},
            "program_sha256": r["program_sha256"],
            "report_sha256": sha(p / "report.json"),
            "state_sha256": sha(p / "state.json"),
        }
    a, b = read(old / "sum/report.json"), read(root / "sum/report.json")
    assert a["repair_ports"] == b["repair_ports"]
    assert all(a["stage_spine"]["stats"][k] == b["stage_spine"]["stats"][k]
               for k in SPINE_FIELDS)
    assert read(root / "semantic-acceptance.json")["status"] == "pass"
    output.write_text(json.dumps({
        "runtime_commit": "a1f3dcb2",
        "scope": "standalone Cell CPU; diagnostic setup correction; no runtime optimization or throughput claim",
        "limits": "Raytrace is a 1280-Run prefix, not a full run or independent native proof. Run records are compared, not per-Run graph snapshots.",
        "comparisons": checks, "cases": cases,
        "prefix_sha256": sha(root / "prefix"),
        "runtime_sha256": sha(root / "runtime"),
        "native_acceptance_sha256": sha(root / "semantic-acceptance.json"),
    }, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
