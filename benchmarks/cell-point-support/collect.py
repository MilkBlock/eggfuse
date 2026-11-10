#!/usr/bin/env python3
"""Validate saved work/allocation checks; never launch a workload."""
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


FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")


def compare(before, after):
    a, b = read(before / "report.json"), read(after / "report.json")
    require(a["program_sha256"] == b["program_sha256"], "different program")
    signature = lambda r: [[s[k] for k in FIELDS] for s in r["steps"]]
    require(signature(a) == signature(b), "ordered Run records differ")
    require(read(before / "state.json") == read(after / "state.json"), "graph differs")
    for k in ("bindings", "constructor_requests", "logical_facts_created", "function_updates", "unions", "single_writes", "transient_writes"):
        require(a["stats"][k] == b["stats"][k], "graph work differs: " + k)
    require(b["point_support_accounting"] == "current-column/v1", "missing work accounting")
    rejected = b["free_join"]["point_support_rejected"]
    require(a["key_lookup_calls"] - b["key_lookup_calls"] == rejected, "saved queries do not reconcile")
    for k in ("completed_steps", "anchor_publications", "ripsat_completed"):
        require(a["stage_spine"]["stats"][k] == b["stage_spine"]["stats"][k], "completion/publication differs")
    return a, b


def collect(root, output):
    cases = {}
    for name, before in (("sum", root.parent / "cell-attribute-profile/sum-normal"),
            ("ray1280", root / "ray1280-before"),
            ("sum-stable", root.parent / "cell-dense-inputs/stable4-before"),
            ("sum-completed", root.parent / "cell-dense-inputs/completed4-before")):
        after = root / name
        a, b = compare(before, after)
        cases[name] = {"runs": len(b["steps"]), "baseline_report_sha256": sha(before / "report.json"),
            "report_sha256": sha(after / "report.json"), "state_sha256": sha(after / "state.json"),
            "lookups": [a["key_lookup_calls"], b["key_lookup_calls"]],
            "support": {k: v for k, v in b["free_join"].items() if k.startswith("point_support_")},
            "indexed_columns": [a["indexed_columns"], b["indexed_columns"]],
            "spine_entries": [a["query_workers"]["stats"]["spine_entries"], b["query_workers"]["stats"]["spine_entries"]],
            "routed_spine_seeds": [a["stage_spine"]["stats"]["routed_spine_seeds"], b["stage_spine"]["stats"]["routed_spine_seeds"]]}
    allocations = {}
    for case in ("sum", "ray1280"):
        a, b = compare(root / f"{case}-before-alloc", root / f"{case}-after-alloc")
        allocations[case] = {"before": a["allocations"], "after": b["allocations"],
            "reports": [sha(root / f"{case}-{v}-alloc/report.json") for v in ("before", "after")]}
    require(read(root / "semantic-acceptance.json")["status"] == "pass", "sum-bits native acceptance failed")
    output.write_text(json.dumps({"baseline_commit": "497d5300",
        "scope": "standalone Cell CPU; bounded work and allocator diagnostics, no throughput or general sparsity claim",
        "cases": cases, "allocations": allocations,
        "binaries": {n: sha(root / n) for n in ("runtime", "prefix", "runtime-before-alloc", "prefix-before-alloc", "runtime-after-alloc", "prefix-after-alloc")},
        "semantic_acceptance_sha256": sha(root / "semantic-acceptance.json")}, indent=2) + "\n")


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
