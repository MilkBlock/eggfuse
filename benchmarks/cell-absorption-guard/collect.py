#!/usr/bin/env python3
"""Check saved absorption experiments, including the omitted matches' premises."""
import gzip
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as f:
        return json.load(f)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def stable_steps(report):
    fields = ("ordinal", "epoch", "ruleset", "path", "iterations", "logical_matches", "changed")
    return [[s[k] for k in fields] for s in report["steps"]]


def summarize(a, b):
    assert a["program_sha256"] == b["program_sha256"]
    assert stable_steps(a) == stable_steps(b)
    for k in ("function_updates", "unions", "logical_facts_created", "constructor_requests", "constructor_reused"):
        assert a["stats"][k] == b["stats"][k], k
    condition = dict(b["neighbor_context"]["absorption"]["stats"])
    assert not any(condition.pop("pending"))
    n = condition["matches_absorbed"]
    for k in ("bindings", "single_writes"):
        assert a["stats"][k] - b["stats"][k] == n, k
    assert sum(s["executed_bindings"] for s in a["steps"]) - sum(s["executed_bindings"] for s in b["steps"]) == n
    assert a["key_lookup_calls"] == b["key_lookup_calls"]
    for k in ("completed_steps", "absorbed_root_completions"):
        assert a["stage_spine"]["stats"][k] - b["stage_spine"]["stats"][k] == n
    assert a["stage_spine"]["stats"]["resumed_steps"] == b["stage_spine"]["stats"]["resumed_steps"]
    return {"runs":len(b["steps"]),"conditions":condition,"logical_runs_and_actual_mutations_equal":True,
        "point_queries":[a["key_lookup_calls"],b["key_lookup_calls"]],
        "allocations":{k:[a["allocations"][k],b["allocations"][k]] for k in ("alloc_calls","realloc_calls","requested_bytes")},
        "entry":{k:[a["entry_schedule"]["stats"][k],b["entry_schedule"]["stats"][k]]
                 for k in ("entry_publication_writes","publication_slot_probes","staged_root_records")},
        "binding_single_write_and_completion_savings":n}


def windows(root):
    result = []
    previous = root.parent / "cell-change-locality/observed"
    checks = read(root / "windows/checks.json")
    assert checks["state_sha256"] == read(previous / "checks.json")["state_sha256"]
    assert stable_steps(read(root/"windows/report.json")) == stable_steps(read(previous/"report.json"))
    for path in sorted((root / "windows").glob("run-*.json.gz")):
        a, b = read(previous / path.name), read(path)
        assert a["before"] == b["before"] and a["after"] == b["after"], path.name
        assert (a["unions_before"],a["unions_after"]) == (b["unions_before"],b["unions_after"])
        # Source ordinals count executed bindings and deliberately change when
        # no-op matches are omitted. Keep the writer rule and every actual effect.
        def writes(w):
            return [{**v,"source":None if v["source"] is None else v["source"][1]}
                    for v in w["capture"]["effective_writes"]]
        assert writes(a) == writes(b), (path.name,"actual ordered mutations")
        def binding(v): return {k:x for k,x in v.items() if k != "ordinal"}
        new = b["capture"]["matches"]
        position = removed = 0
        sizes = {r["values"][0]["Eq"]:r["values"][1]["Int"] for r in a["before"]
                 if r["table"] == "Expr-size" and not r["hidden"]}
        for match in a["capture"]["matches"]:
            if position < len(new) and binding(match) == binding(new[position]):
                position += 1
            else:
                assert match["rule"] == 153 and not match["direct"], (path.name,"uncovered match removed")
                values = match["values"]
                assert sizes[values["2"]["Eq"]] <= values["3"]["Int"], (path.name,"not absorbed before Run")
                removed += 1
        assert position == len(new), (path.name,"new or reordered matching")
        result.append({"run":a["run"],"removed_get_matches":removed,"states_and_ordered_actual_writes_equal":True,
                       "before_sha256":sha(previous/path.name),"after_sha256":sha(path)})
    assert len(result) == 14 and sum(r["removed_get_matches"] for r in result) > 0
    return result


def collect(root, output):
    acceptance = read(root/"semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root/"sum/state.json")
    reviewed = read(Path(__file__).resolve().parent.parent / "cell-change-locality/results.json")
    assert read(root/"ray-full/report.json")["program_sha256"] == reviewed["program_sha256"]
    result = {"baseline_commit":"e1610f4c","scope":"standalone Cell CPU; opt-in structural absorption experiment, no timing claim",
              "limits":"No general sparsity theorem or 2x result. Raytrace relative state and selected Run checks, not independent native proof.",
              "native_sum_acceptance_sha256":sha(root/"semantic-acceptance.json"),"cases":{}}
    for case in ("sum","ray1280","ray-full"):
        control = root/"ray-before" if case == "ray-full" else root.parent/"cell-absorbed-publication"/case
        assert sha(control/"state.json") == sha(root/case/"state.json"), case
        result["cases"][case] = summarize(read(control/"report.json"),read(root/case/"report.json"))
        result["cases"][case]["state_sha256"] = sha(root/case/"state.json")
        result["cases"][case]["reports_sha256"] = [sha(control/"report.json"),sha(root/case/"report.json")]
    full = read(root/"ray-full-equality.json")
    assert full["status"] == "pass" and full["inputs"][1] == sha(root/"ray-full/state.json")
    result["full_rooted_equality"] = full
    old, layout = read(root/"ray-before/report.json"), read(root/"ray-control/report.json")
    assert old["stats"] == layout["stats"] and stable_steps(old) == stable_steps(layout)
    result["disabled_feature_layout_cost"] = {k:[old["allocations"][k],layout["allocations"][k]]
        for k in ("alloc_calls","realloc_calls","requested_bytes")}
    result["windows"] = windows(root)
    result["binaries"] = {name:sha(root/name) for name in ("prefix","observer")}
    output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__: raise SystemExit("run without Python -O")
    collect(*map(Path,sys.argv[1:]))
