#!/usr/bin/env python3
"""Check saved collision-delta exports. No workload execution or timing."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "marker-handoff"))
from audit import equivalent, load


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, output):
    cases = {}
    for case in ("sum", "ray1280"):
        before, after = root.parent / "cell-point-support" / case, root / case
        a, b = load(before / "report.json"), load(after / "report.json")
        assert a["program_sha256"] == b["program_sha256"]
        fields = ("ordinal", "ruleset", "path", "iterations", "epoch", "changed")
        assert len(a["steps"]) == len(b["steps"])
        changes = {}
        for x, y in zip(a["steps"], b["steps"]):
            assert all(x[k] == y[k] for k in fields), (case, x["ordinal"])
            if x["executed_bindings"] != y["executed_bindings"]:
                c = changes.setdefault(x["ruleset"], {"runs": 0, "before": 0, "after": 0})
                c["runs"] += 1
                c["before"] += x["executed_bindings"]
                c["after"] += y["executed_bindings"]
        proof = equivalent(load(before / "state.json"), load(after / "state.json"))
        for k in ("function_updates", "unions", "logical_facts_created", "repaired_dependencies"):
            assert a["stats"][k] == b["stats"][k], (case, k)
        cases[case] = {
            "runs": len(b["steps"]), "exact_final_bijection": proof,
            "source_schedule_and_changed_flags_equal": True,
            "queries": [a["key_lookup_calls"], b["key_lookup_calls"]],
            "work": {k: [a["stats"][k], b["stats"][k]] for k in (
                "bindings", "constructor_requests", "function_updates", "unions",
                "logical_facts_created", "repaired_dependencies", "single_writes")},
            "changed_binding_batches": changes,
            "program_sha256": a["program_sha256"],
            "report_sha256": [sha(p / "report.json") for p in (before, after)],
            "state_sha256": [sha(p / "state.json") for p in (before, after)],
        }
    assert load(root / "semantic-acceptance.json")["status"] == "pass"
    output.write_text(json.dumps({
        "baseline_commit": "d1fba785",
        "scope": "standalone Cell CPU; collision-delta correctness fix and bounded work, no throughput claim",
        "cases": cases,
        "runtime_sha256": sha(root / "runtime"),
        "prefix_sha256": sha(root / "prefix"),
        "sum_native_acceptance_sha256": sha(root / "semantic-acceptance.json"),
    }, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
