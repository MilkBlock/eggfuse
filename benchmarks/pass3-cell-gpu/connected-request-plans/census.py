"""Relate source-only connected request plans to measured original issuance. No test-time inputs to planning."""
import argparse
import hashlib
import json
from pathlib import Path
from lower import lower, validate


def collect(bundle, profiles):
    read = lambda p: json.loads(p.read_bytes())
    rules = read(bundle / "program.json")["recipe"]["rules"]
    plans = read(bundle / "plans.json")
    if len(rules)!=len(plans):
        raise ValueError('source and sealed plan rule counts differ')
    interface=json.dumps([[r["query"] for r in rules],plans],separators=(",",":"),sort_keys=True).encode()
    found = {}
    for i, (rule, plan) in enumerate(zip(rules, plans)):
        if not plan:
            continue
        old = sum(flag for _, flag, _ in plan["ins"])
        if old == plan["width"]:
            continue
        assert old > plan["width"]
        order = lower(rule)
        if order is None:
            continue
        width = validate(rule, order)
        assert width >= plan["width"]
        if width < old:
            found[str(i)] = dict(original=old, lower_bound=plan["width"], connected=width,
                                 order=order, atoms=rule["query"])
    rows = {}
    for name, profile in read(profiles).items():
        matched = [(v, profile["rules"][rid]) for rid, v in found.items() if rid in profile["rules"]]
        rows[name] = dict(profiled_rules=len(matched), emitting_rules=sum(p["raw"] > 0 for _, p in matched),
                          prior_raw=sum(p["raw"] for _, p in matched),
                          prior_root_visits=sum(p["root_visits"] for _, p in matched),
                          prior_issuance_ms=sum(p["issuance_ms"] for _, p in matched))
    return dict(plans=len([p for p in plans if p]), width_gap=sum(
        bool(p and sum(v[1] for v in p["ins"]) > p["width"]) for p in plans),
        source_sha=read(bundle/"program.json")["sha256"], interface_sha=hashlib.sha256(interface).hexdigest(), reduced=found, workloads=rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("bundle", "profiles", "out"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    r = collect(args.bundle, args.profiles)
    args.out.write_text(json.dumps(r, separators=(",", ":"))+"\n")
    print(r["width_gap"], len(r["reduced"]), r["workloads"])
