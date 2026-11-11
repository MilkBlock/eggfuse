#!/usr/bin/env python3
"""Reconcile deleted Cell handoffs and new Entry work; launches no workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compare(a, b):
    fields = ("ordinal", "epoch", "ruleset", "path", "iterations", "logical_matches",
              "executed_bindings", "local_bindings", "changed", "live_cells")
    for field in ("program_sha256", "stats", "key_lookup_calls"):
        assert a[field] == b[field], field
    assert [[s[k] for k in fields] for s in a["steps"]] == [[s[k] for k in fields] for s in b["steps"]]
    x, y = a["stage_spine"]["stats"], b["stage_spine"]["stats"]
    n = y["absorbed_root_completions"]
    assert n > 0
    for field in ("captured_contexts", "completion_cell_visits", "inline_function_receipts", "inline_function_reads"):
        assert x[field] - y[field] == n, field
    for field in ("completed_steps", "anchor_publications", "resumed_steps", "history_capture_reads",
                  "history_slots_written", "root_completion_seeds", "root_attempts"):
        assert x[field] == y[field], field
    assert a["stage_spine"]["completion_record_bytes"] == b["stage_spine"]["completion_record_bytes"] == 104
    u, v = a["entry_schedule"]["stats"], b["entry_schedule"]["stats"]
    assert v["staged_root_records"] == v["staged_root_checks"] == n
    assert v["publication_slot_probes"] - u["publication_slot_probes"] == v["staged_root_redirects"]
    assert v["entry_publication_writes"] - u["entry_publication_writes"] == n - v["staged_root_winners"] + v["staged_root_redirects"]
    for field in ("row_decodes", "private_row_reads", "node_notifications", "retired_packets", "predicate_checks"):
        assert u[field] == v[field], field
    return {"runs":len(b["steps"]),"exact_graph_work_queries_and_ordered_runs":True,
        "queries":b["key_lookup_calls"],"completion_records_removed":n,
        "retained_work":{k:y[k] for k in ("completed_steps","anchor_publications","resumed_steps","history_capture_reads")},
        "completion_record_bytes":b["stage_spine"]["completion_record_bytes"],
        "admission_checks":y["absorbed_root_checks"],
        "entry_work":{k:[u.get(k),v[k]] for k in ("publication_slot_probes","entry_publication_writes",
            "staged_root_records","staged_root_checks","staged_root_redirects","staged_root_winners",
            "peak_staged_roots","staged_root_record_bytes","staged_root_capacity_bytes","publication_slot_bytes")}}


def collect(root, output):
    baseline = root.parent/"cell-entry-row-reuse"
    windows = root.parent/"cell-change-locality"
    acceptance = read(root/"semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root/"sum/state.json")
    result = {"baseline_commit":"9b1844ae", "scope":"standalone Cell CPU; work and allocation diagnostics, not throughput",
        "prefix_baseline_provenance":"991896e8 frozen prefix; 9b1844ae only added an inactive audit feature",
        "cases":{}, "native_sum_acceptance_sha256":sha(root/"semantic-acceptance.json")}
    for case in ("sum","ray1280"):
        a, b = read(baseline/case/"report.json"), read(root/case/"report.json")
        assert read(baseline/case/"state.json") == read(root/case/"state.json")
        assert a["prefix_configuration"] == b["prefix_configuration"]
        r = compare(a,b)
        r["configuration"] = b["prefix_configuration"]
        r["allocations"] = {k:[a["allocations"][k],b["allocations"][k]]
                            for k in ("alloc_calls","realloc_calls","requested_bytes")}
        r["state_sha256"] = sha(root/case/"state.json")
        r["report_sha256"] = [sha(p/case/"report.json") for p in (baseline,root)]
        result["cases"][case] = r
    assert read(windows/"control/checks.json") == read(root/"ray-audit/checks.json")
    assert read(windows/"census/checks.json") == read(root/"census/checks.json")
    # The aggregate per-rule counts contain matches, committed updates and
    # direct tokens, not inferred mutations from logical match cardinality.
    assert read(windows/"census/census.json") == read(root/"census/census.json")
    result["full_raytrace"] = compare(read(windows/"census/report.json"),read(root/"census/report.json"))
    result["full_raytrace"].update({"exact_final_state":True,"fourteen_selected_ordered_audits_equal":True,
        "state_sha256":read(root/"census/checks.json")["state_sha256"],
        "allocation_measurement":None,
        "limits":"Relative frozen Raytrace checks, not an independent native Raytrace proof or every-Run graph export."})
    result["binaries"] = {name:sha(root/name) for name in ("before-prefix","prefix","observer")}
    result["audit_artifacts"] = {f"{lane}/{name}":sha(root/lane/name)
        for lane in ("ray-audit","census") for name in ("report.json","checks.json")}
    output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__: raise SystemExit("assertions require Python without -O")
    collect(*map(Path,sys.argv[1:]))
