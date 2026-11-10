#!/usr/bin/env python3
"""Check saved short runs; no workload or timing executions."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


RUN_FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
FIELDS = ("point_reads", "entry_headers", "entries", "answers", "chunks", "winner_order_comparisons", "answer_buffer_allocations", "fixed_read_probes", "fixed_read_fills", "fixed_read_hits", "fixed_read_clears", "fixed_key_fields", "fixed_rejected_entries", "shared_first_reads", "shared_first_key_fields", "fixed_read_storage_bytes", "compiled_cell_code_bytes", "frame_allocations", "frame_capacity_bytes", "completion_headers")


def collect(root, output):
    cases = {}
    for group in ("sum", "stable", "completed", "ray128"):
        reference = read(root / (group + "-before4") / "report.json")
        graph = read(root / (group + "-before4") / "state.json")
        signature = lambda r: [[s[k] for k in RUN_FIELDS] for s in r["steps"]]
        names = [group + "-before4", group + "-after4"]
        if group in ("sum", "ray128"):
            names += [group + "-before1", group + "-after1"]
        for name in names:
            directory = root / name
            r = read(directory / "report.json")
            require(r["program_sha256"] == reference["program_sha256"], name + " input differs")
            require(r["status"] == ("checkpointed" if group == "ray128" else "complete"), name + " incomplete")
            require(len(r["steps"]) == (128 if group == "ray128" else 1428), name + " Run count")
            require(signature(r) == signature(reference), name + " ordered Run records differ")
            require(read(directory / "state.json") == graph, name + " graph differs")
            w = r["query_workers"]["stats"]
            if "after" in name:
                require(w["fixed_read_fills"] == w["fixed_read_clears"], name + " stale first reads")
                require(w["fixed_read_probes"] == w["fixed_read_fills"] + w["fixed_read_hits"], name + " bad accounting")
                require(reference["key_lookup_calls"] - r["key_lookup_calls"] == w["fixed_read_hits"], name + " query saving differs")
                require(w["entries"] + w["fixed_rejected_entries"] == reference["query_workers"]["stats"]["entries"], name + " Entry loss")
                require(w["entries"] == sum(w["worker_entries"]) + w["coordinator_entries"], name + " worker accounting")
            require(r["stage_spine"]["stats"]["ripsat_completed"] == reference["stage_spine"]["stats"]["ripsat_completed"], name + " completion changed")
            cases[name] = {"report_sha256": sha(directory / "report.json"), "state_sha256": sha(directory / "state.json"),
                "runs": len(r["steps"]), "program_sha256": r["program_sha256"], "key_lookup_calls": r["key_lookup_calls"],
                "ripsat_completed": r["stage_spine"]["stats"]["ripsat_completed"],
                "workers": {k: w.get(k) for k in FIELDS}, "constructors": w["constructors"]}
    require(read(root / "semantic-acceptance.json")["status"] == "pass", "sum-bits native acceptance failed")
    output.write_text(json.dumps({"baseline_commit": "aeb059e0", "scope": "standalone Cell CPU; short work and correctness checks; no speed or general sparsity claim",
        "binaries": {n: sha(root / n) for n in ("runtime-before", "runtime-after", "prefix-before", "prefix-after")},
        "programs": {n: sha(root / n) for n in ("sum-program.json", "ray-program.json", "completed-program.json")},
        "semantic_acceptance": {"status": "pass", "sha256": sha(root / "semantic-acceptance.json")}, "cases": cases}, indent=2) + "\n")


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
