#!/usr/bin/env python3
"""Attribute existing counters from saved reports; run no workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")


def collect(root, output):
    program = root.parent / "cell-fixed-reads/ray-program.json"
    rules = read(program)["recipe"]["rules"]
    family = [i for i, r in enumerate(rules) if any(op["op"] == "set" and op.get("call", {}).get("table") == "Expr-size" for op in r["effects"])]
    cases = {}
    for name, baseline in (("sum-profile", root.parent / "cell-dense-inputs/sum0-before"),
            ("ray1280-profile", root / "ray1280-before"),
            ("ray-profile", root.parent / "cell-fixed-reads/ray-profile-all")):
        directory = root / name
        report = read(directory / "report.json")
        before = read(baseline / "report.json")
        require(report["program_sha256"] == before["program_sha256"], "input differs")
        signature = lambda r: [[s[k] for k in FIELDS] for s in r["steps"]]
        require(signature(report) == signature(before), "ordered Runs differ")
        require(read(directory / "state.json") == read(baseline / "state.json"), "graph differs")
        rows = report["query_rule_profile"]
        for name_rhs, name_global in (("single_writes", "single_writes"), ("unchanged_single_writes", "transient_writes"), ("bindings", "bindings")):
            require(sum(r["rhs"][name_rhs] for r in rows) == report["stats"][name_global], "attribution does not reconcile")
        require(all(r["bindings"] == r["rhs"]["bindings"] for r in rows), "matching/apply attribution differs")
        selected = [r for r in rows if r["rule"] in family]
        totals = {k: sum(r["rhs"][k] for r in selected) for k in selected[0]["rhs"]}
        require(totals["single_writes"] - totals["unchanged_single_writes"] <= totals["function_updates"], "invalid changed-write accounting")
        cases[name] = {"report_sha256": sha(directory / "report.json"), "state_sha256": sha(directory / "state.json"),
            "baseline_report_sha256": sha(baseline / "report.json"), "runs": len(report["steps"]),
            "expr_size": selected, "expr_size_totals": totals,
            "neighbor_rules": {str(i): report["neighbor_context"]["rules"].get(str(i)) for i in family}}
    require(read(root / "semantic-acceptance.json")["status"] == "pass", "native acceptance failed")
    normal = read(root / "sum-normal/report.json")
    require(normal["query_rule_profile"] is None, "normal mode unexpectedly profiles")
    require(read(root / "sum-normal/state.json") == read(root / "sum-profile/state.json"), "normal/profile differ")
    output.write_text(json.dumps({"baseline_commit": "f2a008da", "scope": "standalone Cell CPU, one instrumented attribution; not throughput or general sparsity proof",
        "program_sha256": sha(program), "runtime_sha256": sha(root / "runtime"), "prefix_sha256": sha(root / "prefix"),
        "semantic_acceptance_sha256": sha(root / "semantic-acceptance.json"), "cases": cases}, indent=2) + "\n")


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
