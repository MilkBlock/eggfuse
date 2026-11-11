#!/usr/bin/env python3
"""Check a frozen Raytrace comparison with source-Run hoist witnesses.

This is a relative Cell-runtime contract, not an independent native proof.
All tables except to-hoist retain exact rooted equality, including terms and
markers. Every changed selection must satisfy the original LHS in its input
Run snapshot, and the final selector must be the forwarded last selection.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "marker-handoff"))
from audit import equivalent, key, load
from choice_diagnosis import SOURCE_CORE_SHA256

RAY_SOURCE = "634200282ff2252d38987312d6c1988754dc754f64499a7a6a89228aec27c635"
FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
TABLES = {"to-hoist", "to-hoist-size", "Expr-size", "is-inv-Expr", "DoWhile", "HasType", "Base"}


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for data in iter(lambda: f.read(1 << 20), b""):
            h.update(data)
    return h.hexdigest()


def alpha(rule):
    names = {}
    def go(v, field=None):
        if field in ("var", "dst") and isinstance(v, str):
            return names.setdefault(v, len(names))
        if isinstance(v, dict):
            return {k: go(v[k], k) for k in sorted(v)}
        if isinstance(v, list):
            return [go(x) for x in v]
        return v
    return go(rule)


def contract(sum_program, ray_program):
    a, b = [load(p)["source_core"] for p in (sum_program, ray_program)]
    if hashlib.sha256(key(a).encode()).hexdigest() != SOURCE_CORE_SHA256 or hashlib.sha256(key(b).encode()).hexdigest() != RAY_SOURCE:
        raise ValueError("source is outside the reviewed frozen contract")
    assert {k: v for k, v in a.items() if k not in ("rulesets", "structural_key")} == {
        k: v for k, v in b.items() if k not in ("rulesets", "structural_key")}
    changes, same = [], 0
    assert len(a["rulesets"]) == len(b["rulesets"])
    for x, y in zip(a["rulesets"], b["rulesets"]):
        assert x["name"] == y["name"] and len(x["rules"]) == len(y["rules"])
        for i, (u, v) in enumerate(zip(x["rules"], y["rules"])):
            if alpha(u) == alpha(v):
                same += 1
            else:
                changes.append((x["name"], i))
    assert changes == [("initialization", 0)] and same == 612
    assert {k: v for k, v in a["structural_key"].items() if k != "string_labels"} == {
        k: v for k, v in b["structural_key"].items() if k != "string_labels"}
    for core in (a, b):
        for item in core["structural_key"]["string_labels"]:
            assert item["label"] == "String:" + json.dumps(item["value"], ensure_ascii=False)
    writers = [(rs["name"], op["op"]) for rs in b["rulesets"] for r in rs["rules"]
               for op in r["head"] if op.get("call", {}).get("table") == "to-hoist"]
    assert writers == [("boundary-analysis", "set")]
    return {"source_core_sha256": RAY_SOURCE, "alpha_equivalent_rules": same,
            "changed_rule": changes, "choice_writers": writers}


def tables(state):
    result = {t: [] for t in TABLES}
    for row in state["rows"]:
        if row["table"] in TABLES:
            if row["table"] == "to-hoist":
                assert not row["subsumed"], "hidden selector needs another contract"
            if not row["subsumed"]:
                result[row["table"]].append(row["values"])
    return result


def choices(t):
    result = {key(r[:2]): r[-1] for r in t["to-hoist"]}
    assert len(result) == len(t["to-hoist"]), "duplicate selector key"
    return result


def project_choices(state, roots):
    def project(v):
        return {**v, "eq": roots[v["eq"]]}
    rows = tables(state)["to-hoist"]
    result = {key([project(v) for v in row[:2]]): project(row[-1]) for row in rows}
    if len(result) != len(rows):
        raise ValueError("selector keys merge after capture; requires a collision proof")
    return result


def carried_choices(previous, following, roots):
    assert project_choices(previous, roots) == project_choices(following, roots), "unexplained selection between observed writer Runs"


def valid_source_choices(before, after):
    assert before["unions"] == after["unions"], "boundary Eq changed; needs a mapped snapshot proof"
    a, b = tables(before), tables(after)
    old, new = choices(a), choices(b)
    assert old.keys() <= new.keys(), "selector disappeared"
    invariant = {(key(r[0]), key(r[1])) for r in a["is-inv-Expr"]}
    loops = {(key(r[0]), key(r[1])) for r in a["DoWhile"]}
    bases = {key(r[-1]) for r in a["Base"]}
    typed = {key(r[0]) for r in a["HasType"] if key(r[1]) in bases}
    sizes = {key(r[0]): r[1]["value"] for r in a["Expr-size"]}
    maximum = {key(r[:2]): r[-1]["value"] for r in a["to-hoist-size"]}
    changed = []
    for k, expr in new.items():
        if old.get(k) == expr:
            continue
        inputs, body = json.loads(k)
        e = key(expr)
        assert (key(inputs), key(body)) in loops
        assert (key(body), e) in invariant and e in typed
        assert sizes[e] == maximum[k], "new selection failed original size guard"
        changed.append({"key": json.loads(k), "expr": expr, "size_at_selection": sizes[e]})
    return changed


def window_proof(root, lane, program):
    normal = root / ("ray-fast" if lane == "fast" else "ray-current")
    directory = root / ("windows-fast" if lane == "fast" else "windows-current")
    r, w = [load(p / "report.json") for p in (normal, directory)]
    assert r["program_sha256"] == w["program_sha256"] == load(program)["sha256"]
    assert [[s[k] for k in FIELDS] for s in r["steps"]] == [[s[k] for k in FIELDS] for s in w["steps"]]
    assert sha(normal / "state.json") == sha(directory / "state.json")
    runs = [s["ordinal"] for s in r["steps"] if s["ruleset"] == "boundary-analysis" and s["executed_bindings"]]
    roots = {v["old"]: v["now"] for v in load(directory / "tracked-roots.json")}
    changes, hashes, previous = [], {}, None
    for index, run in enumerate(runs):
        a, b = [load(directory / f"run-{n}.json") for n in (run - 1, run)]
        assert (a["run"], b["run"]) == (run - 1, run)
        assert {row["table"] for row in a["rows"] + b["rows"]} <= TABLES
        if index == 0:
            assert not tables(a)["to-hoist"], "unwitnessed initial choices"
        else:
            carried_choices(previous, a, roots)
        changes.extend(dict(c, run=run) for c in valid_source_choices(a, b))
        previous = b
        for n in (run - 1, run):
            hashes[str(n)] = sha(directory / f"run-{n}.json")
    expected = project_choices(b, roots)
    final = tables(load(normal / "state.json"))
    assert expected == choices(final), "final selector not explained by last published selections"
    sizes = {key(row[0]): row[1]["value"] for row in final["Expr-size"]}
    maximum = {key(row[:2]): row[-1]["value"] for row in final["to-hoist-size"]}
    stale = [{"key": json.loads(k), "expr": v, "final_size": sizes[key(v)], "stored_max": maximum[k]}
             for k, v in expected.items() if sizes[key(v)] != maximum[k]]
    return {"source_runs": runs, "observed_selection_changes": len(changes), "changes": changes,
            "final_choices": len(expected), "final_stale_sizes": stale, "snapshot_sha256": hashes,
            "final_state_sha256": sha(normal / "state.json"), "report_sha256": sha(normal / "report.json"),
            "tracked_roots_sha256": sha(directory / "tracked-roots.json")}


def collect(root, sum_program, ray_program, output):
    result = {"scope": "frozen Raytrace relative Cell comparison with source-Run choice evidence; no native or general scheduling proof",
              "contract": contract(sum_program, ray_program)}
    result["windows"] = {lane: window_proof(root, lane, ray_program) for lane in ("fast", "current")}
    a, b = [load(root / n / "state.json") for n in ("ray-fast", "ray-current")]
    selected = {row["table"] for s in (a, b) for row in s["rows"]} - {"to-hoist"}
    result["exact_other_tables"] = equivalent(a, b, selected)
    result["status"] = "pass"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"], result["exact_other_tables"], flush=True)


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    try:
        collect(*map(Path, sys.argv[1:]))
    except AssertionError as error:
        Path(sys.argv[-1]).write_text(json.dumps({"status": "difference", "reason": str(error)}, indent=2) + "\n")
        raise SystemExit(1)
    except (KeyError, OSError, ValueError) as error:
        Path(sys.argv[-1]).write_text(json.dumps({"status": "inconclusive", "reason": str(error)}, indent=2) + "\n")
        raise SystemExit(2)
