"""Recompute every group's fresh reservation and compact the resulting Run allocation curves."""
import hashlib
import json
import math
from itertools import groupby
from pathlib import Path

from runpy import run_path
driver = run_path(str(Path(__file__).with_name("study.py")))
arguments, settings, source = (driver[k] for k in ("arguments", "settings", "source"))


def apportioned(requests, cap):
    total = sum(requests)
    if total <= cap:
        return requests.copy()
    splits = [divmod(n * cap, total) for n in requests]
    grants = [base for base, _ in splits]
    ranking = sorted(range(len(grants)), key=lambda i: (-splits[i][1], i))
    for i in ranking[:cap - sum(grants)]:
        grants[i] += 1
    return grants


def predict(name, args, x, offers):
    x = x.copy()
    if name in args.heads:
        weights = args.heads[name]
        x[-1] = math.log1p(offers)
    else:
        weights = args.policy["models"]["run"]["coverage"]["weights"]
    z = sum(w * v for w, v in zip(weights, x))
    value = offers / (1 + math.exp(-z)) if name == "fraction" else math.expm1(min(math.log1p(args.cap), max(0, z)))
    maximum = args.cap if name in ("entry", "delay") else min(offers, args.cap)
    return min(maximum, math.floor(value + .5))


def checked_curve(name, args, report):
    rows = report["samples"]
    assert len(rows) == len(report["grants"])
    cursor = 0
    curve = []
    digest = hashlib.sha256()
    for epoch, grouped in groupby(rows, key=lambda r: r[0]):
        records = list(grouped)
        trace = report["grants"][cursor:cursor + len(records)]
        cursor += len(records)
        assert all(t[:2] == r[:2] and t[-2:] == r[-2:] for t, r in zip(trace, records))
        requests = [predict(name, args, r[3], r[4]) for r in records]
        offers = sum(r[4] for r in records)
        grants = apportioned(requests, args.cap) if name == "entry" or offers else [0] * len(records)
        assert grants == [t[3] for t in trace], (name, epoch, grants, [t[3] for t in trace])
        digest.update(json.dumps([r[:3] + r[4:] for r in records], separators=(",", ":")).encode())
        fresh = sum(r[-1] for r in records)
        hits = sum(min(k, r[-1]) for k, r in zip(grants, records))
        curve.append([epoch, offers, fresh, sum(grants), hits])
    totals = [sum(r[i] for r in curve) for i in range(1, 5)]
    c = report["counts"]
    assert totals == [c["offers"], c["fresh"], c["granted"], c["used"]]
    return {"totals": totals, "source": digest.hexdigest(), "curve": curve}


def main():
    args = arguments()
    args.out.mkdir(parents=True, exist_ok=False)
    result = {}
    for case in args.cases:
        program, plans, req = source.common.config(args, case)
        with source.base.session(args.exp / "compact-vanilla-20261121/vanilla-audit", program) as exact:
            gold = exact({"audit": True})
        arms = settings(req, args)
        result[case] = log = {}
        with source.base.session(args.native, program, plans) as infer:
            for name, arm in arms.items():
                if name == "off":
                    continue
                cfg = dict(arm, audit=True, spec_cells=dict(arm["spec_cells"], capture=True))
                v = infer(cfg)
                summary = source.base.summarize(v, gold)
                assert summary["aligned"] and all(summary["checks"].values())
                row = checked_curve(name, args, v["spec_cells"])
                assert name == "entry" or row["source"] == log["entry"]["source"]
                log[name] = row
                print(case, name, row["totals"], flush=True)
        (args.out / "curves.json").write_text(json.dumps(result, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
