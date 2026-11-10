#!/usr/bin/env python3
"""Validate saved normal/learning runs and account for both storage costs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("owner_check", "benchmarks/cell-projected-owner/check.py")
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
read, sha, require = prior.read, prior.sha, prior.require


def main(root, output):
    identity = read(root / "build-identity.json")
    h = hashlib.sha256()
    paths = sorted(Path("engine/cell-runtime/src").rglob("*.rs")) + [
        Path("engine/cell-runtime/Cargo.toml"), Path("engine/cell-runtime/examples/cell_state_allocations.rs")]
    for path in paths:
        h.update(str(path).encode() + b"\0" + path.read_bytes() + b"\0")
    require(h.hexdigest() == identity["runtime_tree_sha256"], "runtime changed since build")
    reports = {n: read(root / n / "report.json") for n in (
        "before", "after", "uncombined-before", "uncombined-after",
        "alloc-normal-before", "alloc-normal-after", "alloc-learn-before", "alloc-learn-after")}
    keys = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    schedule = lambda r: [[s[k] for k in keys] for s in r["steps"]]
    expected = read(root / "before/state.json")
    for name, r in reports.items():
        require(r["status"] == "complete" and len(r["steps"]) == 1428, name + " not complete")
        require(read(root / name / "state.json") == expected, name + " final state")
        require(schedule(r) == schedule(reports["before"]), name + " ordered Runs")
    for a, b in (("before", "after"), ("uncombined-before", "uncombined-after"),
                 ("alloc-normal-before", "alloc-normal-after"), ("alloc-learn-before", "alloc-learn-after")):
        require(prior.work(reports[a]) == prior.work(reports[b]), a + " work changed")
        require(reports[a]["stage_spine"]["iterative_bake"] == reports[b]["stage_spine"]["iterative_bake"], a + " discovery counters")
    for f in ("state.json", "stages.json", "binding-audit.json"):
        require(read(root / "audit-before" / f) == read(root / "audit-after" / f), "fallback " + f)
    traces = {}
    for round_id in range(2):
        file = Path(f"round-{round_id}/cell-history.json")
        require(read(root / "iteration" / file) == read(Path("out/cell-projected-owner/iteration") / file), "Bake history changed")
        traces[str(file)] = sha(root / "iteration" / file)
    require(read(root / "alloc-learn-before/cell-history.json") == read(root / "alloc-learn-after/cell-history.json"), "diagnostic discovery differs")
    trial = read(root / "iteration/round-0-trials.json")[0]
    require(trial["semantic_audit"] is True and trial["work"]["net_saved_operations"] == 2768, "Bake audit/credit")
    rounds = read(root / "iteration/rounds.json")
    hashes = read(Path("benchmarks/cell-history-admission/sum-bits-work.json"))["audit_hashes"]
    for row in rounds:
        for k, v in hashes.items():
            require(row[k] == v, "ordered audit " + k)
    require(rounds[1]["source_program"] == trial["program_sha256"] == reports["after"]["program_sha256"], "wrong selected candidate")
    acceptance = read(root / "semantic-acceptance.json")
    require(acceptance["status"] == "pass", "native acceptance")
    for key, name in (("cpu_legacy", "before"), ("cpu_values", "after")):
        require(acceptance["input_sha256"][key] == sha(root / name / "state.json"), "semantic input " + key)
    a, b = reports["before"], reports["after"]
    layouts = {s + "/" + k: {"before": v, "after": b[s][k]}
               for s in ("entry_schedule", "stage_spine") for k, v in a[s].items()
               if k.endswith("_bytes") and b[s].get(k) != v}
    require(b["stage_spine"]["stats"]["history_allocations"] == 369, "projected owner saving lost")
    require(b["stage_spine"]["published_discovery_storage"]["owners"] == 0, "normal execution retained discovery")
    allocations = {mode: {side: reports[f"alloc-{mode}-{side}"]["allocation_diagnostic"]
                         for side in ("before", "after")} for mode in ("normal", "learn")}
    record = {"status": "pass", "scope": "standalone Cell CPU, full sum-bits; allocator builds excluded from speed admission",
              "performance_admission": "untimed; 2x and general sparsity unproved", "identity": identity,
              "binary_sha256": {n: sha(root / n) for n in ("runtime-before", "runtime-after", "alloc-before", "alloc-after")},
              "program_sha256": b["program_sha256"], "ordered_runs": 1428,
              "unchanged_work_counters": len(prior.work(a)), "layout_changes": layouts,
              "execution_state_bytes": b["stage_spine"]["execution_state_bytes"],
              "allocations": allocations,
              "published_discovery_storage": {m: reports[f"alloc-{m}-after"]["stage_spine"]["published_discovery_storage"] for m in ("normal", "learn")},
              "identical_history_hashes": traces, "audit_hashes": hashes,
              "native_semantic_acceptance": acceptance,
              "validation_log_sha256": {f: sha(root / f) for f in ("unit.log", "unit-default.log", "integration.log", "check-minimal.log", "readme-compile.log", "readme-run.log", "readme-bench.log")}}
    output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    normal = allocations["normal"]
    learn = allocations["learn"]
    print("pass: unchanged execution and discovery; normal request bytes",
          normal["after"]["requested_bytes"] - normal["before"]["requested_bytes"],
          "; learning allocation delta", learn["after"]["alloc_calls"] - learn["before"]["alloc_calls"])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
