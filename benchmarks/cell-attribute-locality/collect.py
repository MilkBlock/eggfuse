#!/usr/bin/env python3
"""Reconcile saved Cell admission work; no workloads or throughput measurement."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect(root, output):
    cases = {}
    baseline = root.parent / "cell-collision-delta"
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    for name, before in (("sum", baseline / "sum"), ("ray1280", baseline / "ray1280"),
                         ("sum-stable", root / "sum-stable-before"),
                         ("sum-completed", root / "sum-completed-before")):
        after = root / name
        a, b = read(before / "report.json"), read(after / "report.json")
        assert a["program_sha256"] == b["program_sha256"]
        assert read(before / "state.json") == read(after / "state.json"), name
        assert [[s[k] for k in fields] for s in a["steps"]] == [[s[k] for k in fields] for s in b["steps"]], name
        for k in ("bindings", "constructor_requests", "logical_facts_created", "function_updates",
                  "unions", "single_writes", "transient_writes"):
            assert a["stats"][k] == b["stats"][k], (name, k)
        for k in ("completed_steps", "anchor_publications", "ripsat_completed"):
            assert a["stage_spine"]["stats"][k] == b["stage_spine"]["stats"][k], (name, k)
        assert a["free_join"]["entry_probes"] == b["free_join"]["entry_probes"]
        saved = a["key_lookup_calls"] - b["key_lookup_calls"]
        assert saved == b["free_join"]["point_support_rejected"] - a["free_join"]["point_support_rejected"]
        assert saved == a["stage_spine"]["stats"]["routed_spine_seeds"] - b["stage_spine"]["stats"]["routed_spine_seeds"]
        cases[name] = {
            "runs": len(b["steps"]), "exact_graph_and_ordered_runs_equal": True,
            "queries": [a["key_lookup_calls"], b["key_lookup_calls"]],
            "support": {k: [a["free_join"][k], b["free_join"][k]] for k in a["free_join"] if k.startswith("point_support_")},
            "worker_entries": [a["query_workers"]["stats"]["spine_entries"], b["query_workers"]["stats"]["spine_entries"]],
            "ripsat_completions": b["stage_spine"]["stats"]["ripsat_completed"],
            "family_entries": {str(i): [r["neighbor_context"]["rules"][str(i)]["stats"]["spine_entries"] for r in (a,b)] for i in (148,151,153,154,155)},
            "program_sha256": b["program_sha256"],
            "report_sha256": [sha(p / "report.json") for p in (before, after)],
            "state_sha256": sha(after / "state.json"),
        }
    profile = read(root / "ray-before-profile/report.json")
    normal = read(baseline / "ray1280/report.json")
    assert profile["program_sha256"] == normal["program_sha256"]
    assert read(root / "ray-before-profile/state.json") == read(baseline / "ray1280/state.json")
    assert [[s[k] for k in fields] for s in profile["steps"]] == [[s[k] for k in fields] for s in normal["steps"]]
    rules = read(root.parent / "cell-fixed-reads/ray-program.json")["recipe"]["rules"]
    family = {i for i, r in enumerate(rules) if any(op["op"] == "set"
        and op.get("call", {}).get("table") == "Expr-size" for op in r["effects"])}
    totals = {k: sum(r["rhs"][k] for r in profile["query_rule_profile"] if r["rule"] in family)
        for k in ("bindings", "function_updates", "unchanged_single_writes")}
    attribution = [{"rule": r["rule"], "matches": r["bindings"],
        "actual_updates": r["rhs"]["function_updates"], "unchanged_writes": r["rhs"]["unchanged_single_writes"]}
        for r in profile["query_rule_profile"] if r["rule"] in (148,151,153,154,155)]
    assert read(root / "semantic-acceptance.json")["status"] == "pass"
    output.write_text(json.dumps({"baseline_commit": "98e0ffd3",
        "scope": "standalone Cell CPU; bounded work checks, no throughput or general sparsity proof",
        "before_ray1280_attribution": attribution, "family_totals": totals, "cases": cases,
        "attribution_report_sha256": sha(root / "ray-before-profile/report.json"),
        "runtime_sha256": sha(root / "runtime"), "prefix_sha256": sha(root / "prefix"),
        "native_acceptance_sha256": sha(root / "semantic-acceptance.json")}, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
