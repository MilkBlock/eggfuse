#!/usr/bin/env python3
"""Check saved allocation experiments; never execute or time workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


RUN_FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")


def collect(root, output):
    cases = {}
    for group, runs in (("sum", 1428), ("ray128", 128)):
        base = root / f"{group}-before-alloc"
        reference = read(base / "report.json")
        graph = read(base / "state.json")
        signature = lambda r: [[s[k] for k in RUN_FIELDS] for s in r["steps"]]
        variants = {}
        directories = [("baseline", base), ("bounded_holes", root / f"{group}-after-alloc")]
        draft = root / f"draft1-{group}-after-alloc"
        if draft.exists():
            directories.append(("immediate_sparse_conversion", draft))
        for variant, directory in directories:
            r = read(directory / "report.json")
            require(r["program_sha256"] == reference["program_sha256"], "different input")
            require(r["status"] == ("complete" if group == "sum" else "checkpointed"), "incomplete run")
            require(len(r["steps"]) == runs, "unexpected Run count")
            require(signature(r) == signature(reference), "ordered Run records differ")
            require(read(directory / "state.json") == graph, "final graph differs")
            require(r["stats"] == reference["stats"], "runtime work differs")
            require(r["key_lookup_calls"] == reference["key_lookup_calls"], "query work differs")
            allocations = r["allocations"]
            variants[variant] = {
                "report_sha256": sha(directory / "report.json"),
                "state_sha256": sha(directory / "state.json"),
                "allocations": allocations,
                "alloc_plus_realloc_calls": allocations["alloc_calls"] + allocations["realloc_calls"],
                "fragment_header_bytes": r["stage_spine"]["query_fragment_header_bytes"],
                "winner_bytes": r["stage_spine"]["query_winner_bytes"],
                "fragment_capacity_bytes": r["stage_spine"]["stats"]["query_fragment_capacity_bytes"],
                "query_lookups": r["key_lookup_calls"],
            }
        cases[group] = {"runs": runs, "program_sha256": reference["program_sha256"], "variants": variants}
    require(read(root / "semantic-acceptance.json")["status"] == "pass", "native sum acceptance failed")
    program = read(root / "sum-program.json")
    rules = program["recipe"]["rules"]
    layouts = [[i for i, s in enumerate(rule["slots"]) if s["definition"] == "query"] for rule in rules]
    report = {
        "baseline_commit": "560faaf7",
        "scope": "standalone Cell CPU; separate allocation diagnostic; no throughput or graph sparsity claim",
        "decision": "reject from production path; compact slots trade bytes for more allocator events",
        "rules": len(rules), "dense_input_layouts": sum(ids == list(range(len(ids))) for ids in layouts),
        "patch_sha256": sha(Path(__file__).with_name("experiment.patch")),
        "binaries": {n: sha(root / n) for n in ("runtime-before-alloc", "prefix-before-alloc", "runtime-after-alloc", "prefix-after-alloc")},
        "semantic_acceptance_sha256": sha(root / "semantic-acceptance.json"),
        "cases": cases,
    }
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
