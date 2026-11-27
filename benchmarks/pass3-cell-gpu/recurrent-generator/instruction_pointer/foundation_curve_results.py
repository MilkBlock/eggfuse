"""Aggregate native curves; retain failed thresholds as censored observations."""

import hashlib
import json
import pickle
import random
import shutil
import sys
from pathlib import Path
from statistics import mean

from competition_results import groups, table

CATS = ("primitive", "half", "short", "medium-half", "medium", "multi")
STEPS = (0, 32, 128, 512)


def read(p):
    return json.loads(p.read_text())


def summarize(d, name, rows, keys, fields):
    table(
        d,
        name,
        [
            dict(zip(keys, k))
            | {"n": len(v)}
            | {x: mean(r[x] for r in v) for x in fields}
            for k, v in sorted(groups(rows, keys).items())
        ],
    )


def exposure(src, cat, size, seed):
    data = [
        pickle.loads((src / f"states-{cat}-1-{i}.pkl").read_bytes())
        for i in range(size)
    ]
    rng = random.Random(seed + 652)
    states = set()
    targets = set()
    result = {}
    end = 2048 if cat == "multi" and size == 24 else 512
    for step in range(end + 1):
        if step in STEPS + (1024, 2048):
            result[step] = (len(states), len(targets))
        if step == end:
            break
        for _ in range(4):
            easy = rng.random() < (0.75 if step < 32 else 0.50 if step < 128 else 0.25)
            i = rng.choice([i for i in range(size) if (i % 4 < 2) == easy])
            j = rng.randrange(len(data[i]))
            states.add((i, j))
            for t in rng.choices(data[i][j][1], k=4):
                targets.add((i, j, t))
    return result


def export(src, d):
    d.mkdir(exist_ok=True, parents=True)
    curves = []
    native = []
    paired = []
    found = []
    frontier = []
    ledger = {}
    for cat in CATS:
        for size, width, fresh in (
            [(n, b, False) for n in (4, 12, 24) for b in (32, 128, 512)]
            + [(48, b, False) for b in (32, 512)]
            + [(12, b, True) for b in (32, 128, 512)]
            if cat == "multi"
            else [(12, 32, False)]
        ):
            for seed in (71, 113):
                tag = ("fresh-" if fresh else "") + f"{cat}-{size}-{width}-{seed}"
                p = src / f"curve-{tag}.json"
                if (cat, size, seed) not in ledger:
                    ledger[cat, size, seed] = exposure(src, cat, size, seed)
                records = read(p)
                if cat == "multi" and size == 24 and width in (32, 512):
                    long = read(src / f"curve-long-{tag}.json")
                    assert all(x["held"] == y["held"] for x, y in zip(records, long))
                    records += long[len(records) :]
                for r in records:
                    step = r["step"]
                    states, unique = ledger[cat, size, seed][step]
                    assert states == r["touched"] and len(r["runs"]) == 8
                    z = {k: v for k, v in r.items() if k != "runs"} | {
                        "cat": cat,
                        "size": size,
                        "width": width,
                        "seed": seed,
                        "fresh": fresh,
                        "unique_targets": unique,
                        "tokens_s": r["samples"] / r["seconds"] if step else 0,
                    }
                    for x in r["runs"]:
                        v = z | {
                            k: x[k]
                            for k in (
                                "i",
                                "arity",
                                "draw",
                                "coverage",
                                "covered",
                                "reference",
                                "ops",
                                "ept",
                                "eps",
                                "wall",
                                "graph",
                                "decisions",
                                "slots",
                                "decode",
                            )
                        }
                        v.update(
                            paid=x["stats"]["paid"],
                            internal=x["stats"].get("internal", 0),
                            higher=x["stats"]["higher_completed"],
                            facts=x["facts"],
                        )
                        native.append(v)
                    keys = ("coverage", "ept", "eps", "decisions", "paid", "wall")
                    curves.append(
                        z | {k: mean(v[k] for v in native[-8:]) for k in keys}
                    )
    table(d, "curves", curves)
    summarize(
        d,
        "learning",
        curves,
        ("cat", "size", "width", "fresh", "step"),
        (
            "trainable",
            "states",
            "touched",
            "unique_targets",
            "samples",
            "seconds",
            "tokens_s",
            "fit",
            "held",
            "coverage",
            "ept",
            "eps",
            "decisions",
            "paid",
        ),
    )
    full = [
        r for r in native if r["size"] == 12 and r["width"] == 32 and not r["fresh"]
    ]
    table(
        d, "autonomous", [{k: v for k, v in r.items() if k != "facts"} for r in native]
    )
    summarize(
        d,
        "interface",
        full,
        ("cat", "arity", "step"),
        ("coverage", "decisions", "paid", "ept", "eps", "higher", "wall"),
    )
    for (step, i, seed, draw), points in groups(
        full, ("step", "i", "seed", "draw")
    ).items():
        base = next(r for r in points if r["cat"] == "primitive")
        for r in points:
            a, b = {str(f) for f in base["facts"]}, {str(f) for f in r["facts"]}
            paired.append(
                {
                    "step": step,
                    "i": i,
                    "seed": seed,
                    "draw": draw,
                    "cat": r["cat"],
                    "same": r["graph"] == base["graph"] and a == b,
                    "lost": len(a - b),
                    "gained": len(b - a),
                    "delta_decisions": r["decisions"] - base["decisions"],
                    "delta_paid": r["paid"] - base["paid"],
                }
            )
    table(d, "matched", paired)
    for keys, rs in groups(full, ("cat", "i", "seed", "draw")).items():
        for threshold in (0.25, 0.4, 0.6):
            hit = next(
                (
                    r
                    for r in sorted(rs, key=lambda x: x["step"])
                    if r["coverage"] >= threshold
                ),
                None,
            )
            found.append(
                dict(zip(("cat", "i", "seed", "draw"), keys))
                | {"threshold": threshold, "reached": hit is not None}
                | {
                    k: hit[k] if hit else ""
                    for k in (
                        "step",
                        "samples",
                        "touched",
                        "unique_targets",
                        "seconds",
                        "coverage",
                        "decisions",
                        "paid",
                    )
                }
            )
    table(d, "first-checkpoint", found)
    for cat in CATS:
        for seed in (71, 113):
            rows = read(src / f"frontier-{cat}-{seed}.json")
            assert len(rows) == 24
            frontier += rows
    table(d, "native-prefix", frontier)
    shutil.copyfile(src / "catalogue-probe.csv", d / "catalogue-probe.csv")

    wake = []
    grads = []
    control = []
    live = []
    evidence = []
    for tag in ("wake", "wake-asym"):
        for is_train, n in ((True, 12), (False, 6)):
            for i in range(n):
                for o in pickle.loads((src / f"{tag}-{is_train}-{i}.pkl").read_bytes()):
                    for s, flags, items in o["states"]:
                        for t, status, g in items:
                            wm, dirty = flags[t[0]]
                            evidence.append(
                                {
                                    "tag": tag,
                                    "train": is_train,
                                    "i": i,
                                    "first": o["first"],
                                    "consumed": o["consumed"],
                                    "run": s["run"],
                                    "epoch": s["epoch"],
                                    "token": t,
                                    "wm": wm,
                                    "dirty": dirty,
                                    "status": status,
                                    "gain": g,
                                }
                            )
        for seed in (71, 113):
            for r in read(src / f"{tag}-fit-{seed}.json"):
                extra = {"tag": tag, "seed": seed, "step": r["step"]}
                wake.extend(x | extra for x in r["rows"])
                grads.extend(x | extra for x in r["grads"])
                live.extend(
                    extra
                    | {k: x[k] for k in ("coverage", "eps", "ept", "ops", "graph")}
                    | {"paid": x["stats"]["paid"]}
                    for x in r["live"]
                )
            control.extend(
                x | {"tag": tag, "seed": seed}
                for x in read(src / f"probe-{tag}-{seed}.json")
            )
    table(d, "wake-evidence", evidence)
    table(d, "wake-gradients", grads)
    table(d, "wake-live", live)
    table(d, "wake-pairs", wake)
    summarize(d, "wake", wake, ("tag", "step", "phase"), ("p", "template", "good"))
    summarize(
        d, "observability", control, ("tag", "step", "phase", "mode"), ("p", "template")
    )
    egg = []
    for case in ("fact", "loopfact", "sum-divisors"):
        for cap, n in ((96, 11), (0, 5)):
            raw = read(src / f"egg-{case}-{cap}.json")
            assert len(raw) == 4 * n, (case, cap, len(raw))
            for key, pair in groups(raw, ("label", "seed")).items():
                x, y = pair
                assert {x["rep"], y["rep"]} == {0, 1} and all(
                    x[k] == y[k] for k in ("facts", "graph", "stats", "ops", "offered")
                )
                baseline = next(
                    r for r in raw if r["label"] == "initial" and r["seed"] == key[1]
                )
                base_facts, current_facts = set(baseline["facts"]), set(x["facts"])
                egg.append(
                    {
                        "label": key[0],
                        "seed": key[1],
                        "case": case,
                        "cap": cap,
                        "graph": x["graph"],
                        "same_initial_graph": x["graph"] == baseline["graph"],
                        "lost_vs_initial": len(base_facts - current_facts),
                        "gained_vs_initial": len(current_facts - base_facts),
                        "covered": x["covered"],
                        "coverage": x["coverage"],
                        "paid": x["stats"]["paid"],
                        "ops": x["ops"],
                        "ept": x["ept"],
                        "eps": mean(r["eps"] for r in pair),
                        "decode": mean(r["decode"] for r in pair),
                        "times": [r["wall"] for r in pair],
                        "untriggered": x["receipts"]["rejected"].get(
                            "untriggered_rule", 0
                        ),
                    }
                )
    table(d, "egg-runs", egg)
    summarize(
        d,
        "egg",
        egg,
        ("case", "cap", "label"),
        ("covered", "coverage", "ept", "eps", "paid", "decode", "untriggered"),
    )
    transfer = []
    identity = []
    for case in ("fact", "loopfact", "sum-divisors"):
        runs = read(src / f"transfer-{case}.json")
        assert len(runs) == 16
        for (cat, seed), pair in groups(runs, ("cat", "seed")).items():
            x, y = pair
            base = next(
                r for r in runs if r["cat"] == "primitive" and r["seed"] == seed
            )
            assert {x["rep"], y["rep"]} == {0, 1} and all(
                x[k] == y[k] for k in ("facts", "graph", "stats", "neural")
            )
            base_set = set(map(str, base["facts"]))
            facts = set(map(str, x["facts"]))
            identity.append(
                {
                    "case": case,
                    "cat": cat,
                    "seed": seed,
                    "same_graph": x["graph"] == base["graph"],
                    "lost": len(base_set - facts),
                    "gained": len(facts - base_set),
                }
            )
            transfer.append(
                {
                    "case": case,
                    "cat": cat,
                    "seed": seed,
                    "extra": x["extra"],
                    "coverage": x["coverage"],
                    "covered": x["covered"],
                    "ops": x["ops"],
                    "paid": x["stats"]["paid"],
                    "neural": x["neural"],
                    "internal": x["stats"].get("internal", 0),
                    "higher_selected": x["stats"].get("higher_selected", 0),
                    "higher_opened": x["stats"].get("higher_opened", 0),
                    "higher_completed": x["stats"]["higher_completed"],
                    "pending": x["pending"],
                    "ept": x["ept"],
                    "eps": mean(r["eps"] for r in pair),
                    "wall": [r["wall"] for r in pair],
                }
            )
    table(d, "egg-transfer-runs", transfer)
    table(d, "egg-transfer-matched", identity)
    summarize(
        d,
        "egg-transfer",
        transfer,
        ("case", "cat"),
        (
            "extra",
            "covered",
            "coverage",
            "ept",
            "eps",
            "paid",
            "neural",
            "internal",
            "higher_selected",
            "higher_opened",
            "higher_completed",
            "pending",
        ),
    )
    receipts = []
    for case in ("fact", "loopfact", "sum-divisors"):
        cases = read(src / f"receipt-check-{case}.json")
        assert len(cases) == 6
        for r in cases:
            assert sum(r["higher_receipts"].values()) == r["stats"]["higher_selected"]
            receipts.extend(
                {
                    "case": case,
                    "cat": r["cat"],
                    "seed": r["seed"],
                    "response": k,
                    "count": v,
                }
                for k, v in sorted(r["higher_receipts"].items())
            )
    table(d, "higher-receipts", receipts)
    (d / "sha256.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(src.iterdir())
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    export(*map(Path, sys.argv[1:]))
