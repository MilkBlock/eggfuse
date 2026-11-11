#!/usr/bin/env python3
"""Offline evidence from actual Cell matches; never authorizes a skipped effect."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys


def read(path):
    with (gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)) as f:
        return json.load(f)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def frozen(value):
    if isinstance(value, dict):
        return tuple((k, frozen(v)) for k, v in sorted(value.items()))
    if isinstance(value, list):
        return tuple(map(frozen, value))
    return value


def operand(arg, slots):
    if "slot" in arg:
        return slots[str(arg["slot"])]
    kind = arg["sort"]["kind"]
    assert kind in ("i64", "String"), ("unsupported literal", arg)
    return {"Int" if kind == "i64" else "Text": arg["literal"]}


def plus(args):
    assert len(args) == 2 and all(set(v) == {"Int"} for v in args)
    value = sum(v["Int"] for v in args)
    assert -(1 << 63) <= value < (1 << 63), "i64 overflow"
    return {"Int": value}


def index(rows):
    result = {}
    for row in rows:
        if row["hidden"]:
            continue
        key = row["table"], frozen(row["values"])
        assert key not in result, ("duplicate visible query row", key)
        result[key] = row
    return result


def evaluate(rule, binding, rows):
    """Check observed input facts, then evaluate this narrow pure scalar RHS."""
    slots = dict(binding["values"])
    inputs = []
    for atom in rule["query"]:
        values = [operand(a, slots) for a in atom["args"]]
        call = atom["call"]
        if "table" in call:
            inputs.append(rows[(call["table"], frozen(values))])
        else:
            assert call == {"primitive": "+", "inputs": ["i64", "i64"], "output": "i64"}
            assert plus(values[:-1]) == values[-1]
    outputs = []
    for op in rule["effects"]:
        if op["op"] == "copy":
            slots[str(op["dst"])] = operand(op["arg"], slots)
        elif op["op"] == "let":
            args = [operand(a, slots) for a in op["args"]]
            call = op["call"]
            if "table" in call:
                # Only an already-matched constructor alias is supported.
                candidates = [r for r in inputs if r["table"] == call["table"]
                              and r["values"][:-1] == args]
                assert len(candidates) == 1, "unproven constructor result"
                value = candidates[0]["values"][-1]
            else:
                assert call == {"primitive": "+", "inputs": ["i64", "i64"], "output": "i64"}
                value = plus(args)
            slots[str(op["dst"])] = value
        else:
            assert op["op"] == "set" and op["call"] == {"table": "Expr-size"}
            key = [operand(a, slots) for a in op["args"]]
            value = operand(op["value"], slots)
            assert len(key) == 1 and set(key[0]) == {"Eq"} and set(value) == {"Int"}
            outputs.append((key[0]["Eq"], value["Int"]))
    assert len(outputs) == 1
    return inputs, outputs[0]


def distribution(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "total": 0}
    total = sum(values)
    active = [v for v in values if v]
    return {"count": len(values), "total": total, "zero": values.count(0),
            **{f"p{p}": values[max(0, math.ceil(len(values)*p/100)-1)] for p in (50, 95, 99)},
            **{f"active_p{p}": active[max(0, math.ceil(len(active)*p/100)-1)] if active else 0 for p in (50, 95, 99)},
            "max": values[-1],
            "top_one_percent_share": sum(values[-max(1, math.ceil(len(values)*.01)):])/total if total else 0}


def analyze(window, recipe, get_rule, previous):
    rows = index(window["before"])
    attributes = {r["values"][0]["Eq"]: r["values"][1]["Int"]
                  for r in rows.values() if r["table"] == "Expr-size"}
    current = dict(attributes)
    writes = window["capture"]["effective_writes"]
    # Source effects precede repair. Do not silently attribute a repair change
    # to a successful rule or treat final canonical IDs as source-time IDs.
    rhs_writes = [w for w in writes if w["source"] is not None]
    sources = [w["source"][0] for w in rhs_writes]
    assert sources == sorted(sources), "RHS effect order changed"
    by_source = collections.defaultdict(list)
    for w in rhs_writes:
        by_source[tuple(w["source"])].append(w)
    pointer = 0
    counts = collections.defaultdict(collections.Counter)
    delta = collections.Counter()
    repeats = collections.Counter()
    fanout = collections.Counter()
    changed = collections.defaultdict(set)
    owners = collections.defaultdict(set)
    outputs = collections.defaultdict(set)
    get_neighbors = collections.defaultdict(list)
    for r in rows.values():
        if r["table"] == "Get":
            get_neighbors[r["values"][0]["Eq"]].append(r)
    wm = window["capture"]["watermarks"].get(str(get_rule))
    fresh = {frozen(r["witness"]) for r in rows.values() if r["table"] == "Expr-size"
             and wm is not None and r["epoch"] >= wm}

    def replay(w):
        key = w["key"][0]["Eq"]
        assert w["old"] == (None if key not in current else {"Int": current[key]}), ("write old", window["run"], w)
        current[key] = w["new"]["Int"]

    for b in window["capture"]["matches"]:
        rid = b["rule"]
        inputs, (key, proposed) = evaluate(recipe["rules"][rid], b, rows)
        c = counts[str(rid)]
        c["matches"] += 1
        c["direct_token"] += b["direct"]
        assert b["watermark"] is not None
        new_inputs = [r for r in inputs if r["epoch"] >= b["watermark"]]
        c["without_fresh_input"] += not new_inputs
        while pointer < len(rhs_writes) and rhs_writes[pointer]["source"][0] < b["ordinal"]:
            replay(rhs_writes[pointer]); pointer += 1
        old = current.get(key)
        events = by_source.get((b["ordinal"], rid), [])
        assert len(events) <= 1
        improves = old is None or proposed < old
        assert bool(events) == improves, ("min outcome", window["run"], rid, key, old, proposed, events)
        if events:
            assert events[0]["key"] == [{"Eq": key}] and events[0]["new"] == {"Int": proposed}
        c["effective_updates"] += improves
        c["absorbed_writes"] += not improves
        if key in attributes and attributes[key] <= proposed:
            c["absorbed_before_run"] += 1
        elif not improves:
            c["absorbed_by_earlier_rhs"] += 1

        if rid != get_rule:
            continue
        constructor, attribute = inputs
        assert constructor["table"] == "Get" and attribute["table"] == "Expr-size"
        category = ("constructor" if constructor["epoch"] >= b["watermark"] else "")
        category += ("+attribute" if attribute["epoch"] >= b["watermark"] else "")
        delta[category or "neither"] += 1
        identity = frozen(constructor["witness"])
        signature = (frozen(constructor["values"]), frozen(attribute["values"]),
                     constructor["epoch"], attribute["epoch"])
        old_signature = previous.get(identity)
        if old_signature is None:
            repeats["first_observed"] += 1
        elif old_signature == signature:
            repeats["same_values_and_epochs"] += 1
        elif old_signature[:2] == signature[:2]:
            repeats["same_values_new_epoch"] += 1
        elif old_signature[0] == signature[0]:
            repeats["same_constructor_changed_attribute"] += 1
        else:
            repeats["changed_constructor_fields"] += 1
        previous[identity] = signature
        w = frozen(attribute["witness"])
        if w in fresh:
            fanout[w] += 1
            outputs[w].add(key)
            owners[w].add(constructor["witness"]["Fact"]["cell"])
            if improves:
                changed[w].add(key)

    while pointer < len(rhs_writes):
        replay(rhs_writes[pointer]); pointer += 1
    # Only union-free windows allow an exact ID-preserving post-state replay.
    # Other windows still validate every recorded source-time min effect.
    union_free = window["unions_before"] == window["unions_after"]
    if union_free:
        assert not [w for w in writes if w["source"] is None]
        after = {r["values"][0]["Eq"]: r["values"][1]["Int"] for r in window["after"]
                 if r["table"] == "Expr-size" and not r["hidden"]}
        assert current == after
    samples = {"successful_get_uses": [fanout[w] for w in fresh],
               "distinct_get_outputs": [len(outputs[w]) for w in fresh],
               "changed_get_outputs": [len(changed[w]) for w in fresh],
               "constructor_storage_cells": [len(owners[w]) for w in fresh]}
    groups = collections.Counter()
    for r in rows.values():
        w = frozen(r["witness"])
        if r["table"] != "Expr-size" or w not in fresh:
            continue
        key, proposed = r["values"][0]["Eq"], r["values"][1]["Int"]
        neighbors = get_neighbors[key]
        assert len(neighbors) == fanout[w], ("incomplete fresh-attribute Get coverage", window["run"], key)
        if not neighbors:
            continue
        groups["active_groups"] += 1
        if all(n["values"][-1]["Eq"] in attributes
               and attributes[n["values"][-1]["Eq"]] <= proposed for n in neighbors):
            groups["all_outputs_absorb_before_run"] += 1
            groups["uses_in_absorbed_groups"] += len(neighbors)
    return {"run":window["run"], "rules":dict(counts), "get_delta":dict(delta),
            "get_repeat":dict(repeats), "union_free_post_state_checked":union_free,
            "get_groups":dict(groups),
            "repair_attribute_changes":sum(w["source"] is None for w in writes),
            "fresh_attribute_fanout":{k:distribution(v) for k,v in samples.items()}}, samples


def collect(root, program, reference, output):
    recipe = read(program)["recipe"]
    attribute = next(t for t in recipe["tables"] if t["name"] == "Expr-size")
    assert attribute["merge_expr"] == {"call":{"primitive":"min","inputs":["i64","i64"],"output":"i64"},
                                       "args":[{"var":"old"},{"var":"new"}]}
    get_rule, = [i for i,r in enumerate(recipe["rules"]) if len(r["query"]) == 2
                 and [a["call"] for a in r["query"]] == [{"table":"Get"},{"table":"Expr-size"}]
                 and any(o["op"] == "set" and o["call"] == {"table":"Expr-size"} for o in r["effects"])]
    a, b = [read(root/lane/"checks.json") for lane in ("control","observed")]
    assert a == b, "observer changed selected ordered bindings/effects/resumes or bounded final state"
    ra, rb = [read(root/lane/"report.json") for lane in ("control","observed")]
    assert ra["program_sha256"] == rb["program_sha256"]
    assert ra["stats"] == rb["stats"] and ra["key_lookup_calls"] == rb["key_lookup_calls"]
    fields = ("ordinal","epoch","ruleset","path","iterations","logical_matches","local_bindings",
              "executed_bindings","changed","live_cells")
    assert [[s[k] for k in fields] for s in ra["steps"]] == [[s[k] for k in fields] for s in rb["steps"]]
    census = read(root/"census/census.json")
    cr = read(root/"census/report.json")
    cc = read(root/"census/checks.json")
    rr = read(reference/"report.json")
    assert cc["complete"] and cr["status"] == rr["status"] == "complete"
    assert cr["program_sha256"] == rr["program_sha256"] == ra["program_sha256"]
    assert cc["state_sha256"] == sha(reference/"state.json")
    assert cr["stats"] == rr["stats"] and cr["key_lookup_calls"] == rr["key_lookup_calls"]
    assert [[s[k] for k in fields] for s in cr["steps"]] == [[s[k] for k in fields] for s in rr["steps"]]
    census_rules = collections.defaultdict(lambda: [0,0,0])
    for _, rid, counts in census["counts"]:
        for i, n in enumerate(counts): census_rules[str(rid)][i] += n
    get_runs = [(epoch,counts) for epoch,rid,counts in census["counts"] if rid == get_rule]
    result, samples, previous = [], collections.defaultdict(list), {}
    totals, delta, repeats = collections.defaultdict(collections.Counter), collections.Counter(), collections.Counter()
    groups = collections.Counter()
    paths = sorted((root/"observed").glob("run-*.gz"),key=lambda p:int(p.name.split("-")[1].split(".")[0]))
    assert [int(p.name.split("-")[1].split(".")[0]) for p in paths] == [w["run"] for w in a["windows"]]
    for path in paths:
        r, s = analyze(read(path), recipe, get_rule, previous)
        result.append(r)
        for k,v in r["rules"].items(): totals[k].update(v)
        delta.update(r["get_delta"]); repeats.update(r["get_repeat"])
        groups.update(r["get_groups"])
        for rid, counts in r["rules"].items():
            assert [counts["matches"],counts["effective_updates"],counts["direct_token"]] == next(
                c for epoch, rule, c in census["counts"] if epoch == r["run"] and rule == int(rid))
        for k,v in s.items(): samples[k].extend(v)
    output.write_text(json.dumps({"baseline_commit":"991896e8", "scope":"standalone Cell CPU, selected successful matches; no timing or sparsity theorem",
        "observer_binary_sha256":sha(root/"observer"),
        "program_sha256":rb["program_sha256"], "program_file_sha256":sha(program),
        "observer_control_equal":True, "state_sha256":a["state_sha256"],
        "get_rule":get_rule,"rules":dict(totals),"get_delta":dict(delta),"get_repeat":dict(repeats),
        "get_groups":dict(groups),
        "full_census":{"rule_counts_match_write_direct":dict(census_rules),
            "get_run_count":len(get_runs),"largest_get_runs":sorted(get_runs,key=lambda x:x[1][0],reverse=True)[:20],
            "state_sha256":cc["state_sha256"],"reference_report_sha256":sha(reference/"report.json"),
            "counts_sha256":sha(root/"census/census.json"),"exact_graph_counts_and_all_run_records_equal":True},
        "fresh_attribute_fanout":{k:distribution(v) for k,v in samples.items()},"windows":result,
        "artifacts":{str(p.relative_to(root)):sha(p) for p in paths + [root/lane/name
            for lane in ("census","observed","control") for name in ("checks.json","report.json")]}}, indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("assertions require Python without -O")
    collect(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
