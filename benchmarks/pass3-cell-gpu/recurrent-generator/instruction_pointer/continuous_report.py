"""Collect signed runs without merging effective origins, factual Coverage and named IDs."""

import csv
import gzip
import hashlib
import itertools
import json
import pickle
import sys
from collections import Counter
from pathlib import Path
from statistics import median


def rows(p):
    with gzip.open(p, "rb") as f:
        return pickle.load(f)


def read(p):
    return json.loads(p.read_text())


def save(p, v):
    p.write_text(json.dumps(v, indent=1, sort_keys=True) + "\n")


def csvfile(dest, rs):
    with dest.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rs)


def audit(rs):
    out = Counter()
    by_addr = {}
    last = {}
    examples = []
    for r in rs:
        refs = tuple(map(tuple, r["refs"]))
        name = r["tid"], refs
        addr = r["tid"], tuple(p[:2] for p in refs)
        if addr in by_addr and by_addr[addr] != refs:
            out["version_changed"] += 1
            out["version_changed_productive"] += bool(r["effective_ops"])
        by_addr[addr] = refs
        kind = r["kind"]
        out[kind] += 1
        if kind == "cross_submit":
            prev = last[name]
            assert prev["uid"] == r["previous_uid"]
            out["cross_" + r["status"]] += 1
            out["cross_effective_ops"] += r["effective_ops"]
            out["cross_productive"] += bool(r["effective_ops"])
            out["cross_run_change"] += r["changed_run"]
            out["previous_productive"] += bool(prev["effective_ops"])
            if not examples or (r["effective_ops"] and len(examples) < 10):
                examples.append([prev, r])
        last[name] = r
    return dict(out), examples


def report(raw, out):
    out.mkdir(exist_ok=True, parents=True)
    cases = ("fact", "loopfact", "sum-divisors")
    curves = []
    facts = {}
    repeats = {}
    repeat_rows = []
    profiles = {}
    branches = []
    pairs = []
    models = {}
    manifests = {}
    for case in cases:
        prev = raw.parent / "joint-cell-pretraining"
        entries = rows(prev / f"live-{case}-full-expanded-71-193.pkl.gz")
        repeats[case] = audit(entries)
        by_uid = {r["uid"]: r for r in entries}
        for record in entries:
            if record["kind"] == "cross_submit":
                prior = by_uid[record["previous_uid"]]
                repeat_rows.append(
                    {
                        "case": case,
                        "tid": record["tid"],
                        "refs": json.dumps(record["refs"], separators=(",", ":")),
                        "prior_id": prior["uid"],
                        "id": record["uid"],
                        "prior_run": prior["run"],
                        "run": record["run"],
                        "prior_epoch": prior["epoch"],
                        "epoch": record["epoch"],
                        "prior_dirty": prior["dirty"],
                        "dirty": record["dirty"],
                        "prior_watermark": prior["wm"],
                        "watermark": record["wm"],
                        "prior_status": prior["status"],
                        "status": record["status"],
                        "prior_ops": prior["effective_ops"],
                        "ops": record["effective_ops"],
                    }
                )
        models[case] = dict(
            read(prev / f"{case}-sweep-71.json"),
            checkpoint_sha256=hashlib.sha256(
                (prev / f"{case}-sweep-71.pt").read_bytes()
            ).hexdigest(),
        )
        for budget, seed, arm in itertools.product(
            ("16", "32", "64", "128", "256", "full"),
            (193, 307),
            ("A", "B", "C", "iid", "random", "history"),
        ):
            name = f"{case}-{budget}-{seed}-{arm}"
            r = read(raw / (name + ("-ledger" if arm == "history" else "") + ".json"))
            native = r.get("stats", {})
            repeat = r.get("repeat", {})
            verdict = r.get("verdicts", r.get("receipts", {}).get("rejected", {}))
            paid = native.get("paid", r.get("paid"))
            assert budget == "full" or paid <= int(budget)
            if arm in ("A", "B"):
                base = read(raw / (f"{case}-{budget}-{seed}-A.json"))
                assert (
                    base["graph"] == r["graph"]
                    and base["facts"] == r["facts"]
                    and base["receipts"] == r["receipts"]
                )
            curves.append(
                {
                    "case": case,
                    "cap": budget,
                    "seed": seed,
                    "arm": arm,
                    "paid": paid,
                    "covered": r["covered"],
                    "reference": r["reference"],
                    "coverage": r["coverage"],
                    "ops": r["ops"],
                    "productive_names": r["productive_names"],
                    "productive_entries": r["productive_entries"],
                    "downstream": r["downstream_productive_entries"],
                    "ept": r["ept"],
                    "eps": r["eps"],
                    "wall": r["wall"],
                    "cross_submit": repeat.get("cross_submit", 0)
                    if arm != "history"
                    else "",
                    "duplicate": verdict.get(
                        "duplicate", r.get("receipts", {}).get("duplicates", 0)
                    ),
                    "binding": verdict.get("binding", 0),
                    "untriggered": verdict.get("untriggered_rule", 0),
                    "guard": verdict.get("guard", 0),
                    "higher_selected": native.get("higher_selected", 0),
                    "higher_completed": native.get("higher_completed", 0),
                    "higher_ops": r.get("higher_ops", 0),
                    "internal_paid": native.get("internal", 0),
                    "slots": r.get("counts", {}).get("slots", ""),
                    "visits": r.get("network_calls", {}).get(
                        "candidate_rows", r.get("work", {}).get("visits", "")
                    ),
                    "state_encodes": r.get("counts", {}).get("state_encodes", ""),
                    "reuse": r.get("counts", {}).get("exact_view_reuse", 0),
                    "graph": r["graph"],
                }
            )
            facts[name] = r["facts"]
        forkrows = read(raw / f"forks-{case}.json")
        branches.extend(dict(r, case=case) for r in forkrows)
        for (stage, tail), rs in itertools.groupby(
            forkrows, key=lambda r: (r["threshold"], r.get("tail"))
        ):
            for x, y in itertools.combinations(rs, 2):
                lp = x["anchor"]["logp"][x["choice"]] - y["anchor"]["logp"][y["choice"]]
                gain = x["future"] + x["immediate"] - y["immediate"] - y["future"]
                pairs.append(
                    {
                        "case": case,
                        "threshold": stage,
                        "tail": tail,
                        "x": x["choice"],
                        "y": y["choice"],
                        "delta_logp": lp,
                        "delta_total": gain,
                        "delta_future": x["future"] - y["future"],
                        "delta_facts": x["covered"] - y["covered"],
                    }
                )
        for cap, tag, num, arms in [
            ("256", "t", 4, ("A", "flat")),
            ("256", "p", 4, ("A", "exact")),
            ("full", "paired", 2, ("A", "exact", "random")),
        ]:
            for i in range(num):
                base = read(raw / f"{case}-{cap}-193-A-{tag}{i}.json")
                for arm in arms:
                    p = raw / f"{case}-{cap}-193-{arm}-{tag}{i}.json"
                    r = read(p)
                    match = all(
                        r[k] == base[k]
                        for k in ("facts", "graph", "receipts", "ops", "stats")
                    )
                    if arm == "exact":
                        assert match
                        assert rows(p.with_suffix(".pkl.gz")) == rows(
                            raw / f"{case}-{cap}-193-A-{tag}{i}.pkl.gz"
                        )
                    profiles[p.stem] = {
                        k: r[k]
                        for k in (
                            "ops",
                            "wall",
                            "eps",
                            "profile",
                            "network_times",
                            "network_calls",
                            "transport",
                            "graph",
                        )
                    }
                    profiles[p.stem]["matches_baseline"] = match
        manifests[case] = read(raw / f"device-{case}.json")
    csvfile(out / "native.csv", curves)
    csvfile(out / "repeat-ledger.csv", repeat_rows)
    save(out / "facts.json", facts)
    save(out / "profiles.json", profiles)
    save(out / "historical-repeats.json", repeats)
    save(out / "forks.json", branches)
    csvfile(out / "fork-rank.csv", pairs)
    save(out / "device.json", manifests)
    r = read(raw / "fact-16-193-A.json")
    save(
        out / "training.json",
        {
            "total_parameters": r["parameters"],
            "ce_parameters": r["ce_parameters"],
            "new_trainable": 0,
            "new_exposures": 0,
            "new_seconds": 0,
            "prior_sweep": models,
        },
    )
    summary = []
    for (case, cap, arm), group in itertools.groupby(
        sorted(curves, key=lambda r: (r["case"], r["cap"], r["arm"])),
        key=lambda r: (r["case"], r["cap"], r["arm"]),
    ):
        g = list(group)
        summary.append(
            dict(
                case=case,
                cap=cap,
                arm=arm,
                **{
                    k: median(r[k] for r in g)
                    for k in (
                        "paid",
                        "covered",
                        "coverage",
                        "productive_names",
                        "downstream",
                        "ops",
                        "ept",
                        "eps",
                        "duplicate",
                        "binding",
                        "untriggered",
                        "higher_completed",
                    )
                },
            )
        )
    csvfile(out / "budget-summary.csv", summary)


if __name__ == "__main__":
    report(*map(Path, sys.argv[1:]))
