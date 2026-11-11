#!/usr/bin/env python3
"""Summarize saved semantic, allocation and timing evidence; run no workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def collect(root, output):
    source = read(root / "timing/samples.json")
    proof = read(root / "ray-window-acceptance.json")
    assert proof["status"] == "pass" and read(root / "sum-acceptance.json")["status"] == "pass"
    assert source["finished_at_utc"]
    result = {"candidate_commit": "4cfd0f7e", "historical_fast_commit": "8fffff65778cf8a20de5abdf9b21af69d0358449",
              "scope": source["scope"], "limits": source["limits"], "runtime_sha256": source["runtime_sha256"],
              "raw_samples_sha256": sha(root / "timing/samples.json"), "proof_sha256": source["proof_sha256"],
              "cases": {}, "source_window_contract": proof["contract"], "exact_other_tables": proof["exact_other_tables"],
              "choice_windows": {lane: {k: v[k] for k in ("source_runs", "observed_selection_changes", "final_choices", "final_stale_sizes")}
                                 for lane, v in proof["windows"].items()}}
    work = ("bindings", "function_updates", "unions", "logical_facts_created", "single_writes", "repaired_dependencies")
    for case, data in source["cases"].items():
        entry = result["cases"][case] = {k: data[k] for k in ("repeat", "warmups", "program_sha256", "comparisons")}
        entry["lanes"] = {}
        for name, lane in data["lanes"].items():
            assert len(lane["samples"]) == data["repeat"] and len(lane["warmups"]) == 1
            expected = data["references"]["fast" if name == "fast" else "current"]
            for sample in lane["samples"] + lane["warmups"]:
                assert all(sample[k] == v for k, v in expected.items())
                assert sample["allocations"] is None
            first = lane["samples"][0]
            entry["lanes"][name] = {"timing": lane["timing"], "phases": lane["phases"], "args": lane["args"],
                "queries": first["key_lookup_calls"], "execution_counts": {k: first["stats"][k] for k in work},
                "samples": [{k: s[k] for k in ("iteration", "inference_seconds", "process_wall_seconds")} for s in lane["samples"]]}
    profile = read(root / "ray-profile/report.json")
    normal = read(root / "ray-current/report.json")
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    assert [[s[k] for k in fields] for s in profile["steps"]] == [[s[k] for k in fields] for s in normal["steps"]]
    assert sha(root / "ray-profile/state.json") == sha(root / "ray-current/state.json")
    rules = read(root / "ray-program.json")["recipe"]["rules"]
    family = {i for i, r in enumerate(rules) if any(o["op"] == "set" and o.get("call", {}).get("table") == "Expr-size" for o in r["effects"])}
    rows = profile["query_rule_profile"]
    selected = [r for r in rows if r["rule"] in family]
    result["current_full_profile"] = {
        "scope": "one instrumented serial diagnostic; query timers are not total runtime shares",
        "report_sha256": sha(root / "ray-profile/report.json"),
        "expr_size_query_fraction": sum(r["search_s"] for r in selected) / sum(r["search_s"] for r in rows),
        "expr_size_rhs": {k: sum(r["rhs"][k] for r in selected) for k in ("bindings", "function_updates", "unchanged_single_writes")},
        "top_query_rules": [{"rule": r["rule"], "search_s": r["search_s"], "bindings": r["bindings"],
                             "residual_visits": r["residual_visits"], "rhs": r["rhs"]}
                            for r in sorted(rows, key=lambda r: r["search_s"], reverse=True)[:8]],
    }
    experiment = root.parent / "cell-row-reuse"
    result["rejected_row_reuse"] = {}
    for case in ("sum", "ray1280"):
        a, b = [read(experiment / (case + suffix) / "report.json") for suffix in ("-alloc-before", "-alloc")]
        assert read(experiment / (case + "-alloc-before/state.json")) == read(experiment / (case + "-alloc/state.json"))
        assert [[s[k] for k in fields] for s in a["steps"]] == [[s[k] for k in fields] for s in b["steps"]]
        result["rejected_row_reuse"][case] = {"reuse_checks": b["stats"]["function_row_reuse_checks"],
            "reuses": b["stats"]["function_row_reuses"],
            "allocations": {k: [a["allocations"][k], b["allocations"][k]] for k in ("alloc_calls", "realloc_calls", "requested_bytes")}}
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(*map(Path, sys.argv[1:]))
