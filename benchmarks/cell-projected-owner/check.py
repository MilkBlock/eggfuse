#!/usr/bin/env python3
"""Check saved executions of the projected-owner change; does not run workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def work(report):
    sections = ("stats", "stage_spine/stats", "stable_ports/stats", "cell_ownership/stats", "entry_schedule/stats")
    result = {}
    def visit(prefix, value):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(prefix + "/" + key, child)
        elif type(value) is int:
            result[prefix] = value
    for section in sections:
        value = report
        for key in section.split("/"):
            value = value[key]
        visit(section, value)
    result["key_lookup_calls"] = report["key_lookup_calls"]
    return result


def main(root, output):
    identity = read(root / "build-identity.json")
    for name, digest in identity["runtime_source_sha256"].items():
        require(sha(Path(name)) == digest, "runtime source changed since build: " + name)
    names = ("round0-before", "round0-after", "before-normal", "after-normal")
    reports = {name: read(root / name / "report.json") for name in names}
    keys = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    schedule = lambda r: [[s[k] for k in keys] for s in r["steps"]]
    reference = reports["before-normal"]
    state = read(root / "before-normal/state.json")
    for name, report in reports.items():
        require(report["status"] == "complete", name + " incomplete")
        require(len(report["steps"]) == 1428, name + " Run count")
        require(schedule(report) == schedule(reference), name + " ordered Runs differ")
        require(read(root / name / "state.json") == state, name + " final state differs")
    require(work(reports["round0-before"]) == work(reports["round0-after"]), "uncombined work changed")
    before, after = reports["before-normal"], reports["after-normal"]
    a, b = work(before), work(after)
    require(a.keys() == b.keys(), "counter set changed")
    changed = {k: {"before": a[k], "after": b[k]} for k in a if a[k] != b[k]}
    require(changed == {"stage_spine/stats/history_allocations": {"before": 534, "after": 369}}, "unexpected work change")
    require(after["stage_spine"]["stats"]["ripsat_completed"] == 165, "direct path inactive")
    for name in ("state.json", "stages.json", "binding-audit.json"):
        require(read(root / "before" / name) == read(root / "after-audit" / name), "fallback audit differs: " + name)
    prior = read(Path("benchmarks/cell-history-admission/sum-bits-work.json"))
    rounds = read(root / "iteration/rounds.json")
    trial = read(root / "iteration/round-0-trials.json")[0]
    require(trial["semantic_audit"] is True, "ordered-effect audit failed")
    require(trial["program_sha256"] == prior["candidate_program"] == after["program_sha256"], "candidate changed")
    require(rounds[0]["source_program"] == prior["source_program"] == reports["round0-before"]["program_sha256"], "source changed")
    for row in rounds:
        for key, value in prior["audit_hashes"].items():
            require(row[key] == value, "ordered audit changed: " + key)
    require(trial["work"]["net_saved_operations"] == 2768, "unexpected score")
    require(rounds[1]["source_program"] == trial["program_sha256"], "next round lost measured candidate")
    acceptance = read(root / "semantic-acceptance.json")
    require(acceptance["status"] == "pass", "native semantic acceptance did not pass")
    for key, name in (("cpu_legacy", "before-normal"), ("cpu_values", "after-normal")):
        require(acceptance["input_sha256"][key] == sha(root / name / "state.json"), "semantic input changed: " + key)
    layouts = {}
    for section in ("entry_schedule", "stage_spine"):
        for key, value in before[section].items():
            if key.endswith("_bytes") and after[section].get(key) != value:
                layouts[section + "/" + key] = {"before": value, "after": after[section][key]}
    record = {
        "scope": "standalone Cell CPU executing sum-bits; not native egglog throughput",
        "status": "pass",
        "performance_admission": "unmeasured; fewer owner allocations, larger inline history handles",
        "identity": identity,
        "binary_sha256": {n: sha(root / n) for n in ("runtime-before", "runtime-after")},
        "source_program": prior["source_program"], "candidate_program": prior["candidate_program"],
        "changed_work": changed, "unchanged_work_counters": len(a) - len(changed),
        "layout_costs": layouts,
        "reachable_history_storage": {"before": before["stage_spine"]["published_history_storage"],
                                      "after": after["stage_spine"]["published_history_storage"]},
        "ordered_runs": len(reference["steps"]), "audit_hashes": prior["audit_hashes"],
        "equal_weight_admission_score": {"before": prior["net_saved_operations"], "after": trial["work"]["net_saved_operations"]},
        "native_semantic_acceptance": acceptance,
        "validation": {name: sha(root / name) for name in (
            "unit.log", "unit-default.log", "check-minimal.log", "integration.log",
            "readme-compile.log", "readme-run.log", "readme-bench.log")},
    }
    output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print("pass: 165 owner allocations removed; 8 extra bytes per history handle; speed unmeasured")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
