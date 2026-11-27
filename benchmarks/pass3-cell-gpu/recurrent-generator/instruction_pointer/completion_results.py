"""Summarize certified next-Cell sets and complete independently executed EggCC runs."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

SIZES = (4, 8, 16, 32, 64, 128, 256, 1024)
SEEDS = (9633, 5003, 1777)
VARIANTS = (
    "pair",
    "typed-noise",
    "rules2",
    "rules4",
    "unary",
    "triple",
    "many",
    "prefix",
)


def read(p):
    return json.loads(p.read_bytes())


def save(p, rows):
    with p.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def pooled(rows, fields, cols, func=mean):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in fields)].append(r)
    return [
        dict(
            zip(fields, key),
            **{k: func(r[k] for r in rs) for k in cols},
            replicates=len(rs),
        )
        for key, rs in sorted(groups.items())
    ]


def results(d, out):
    out.mkdir(exist_ok=True, parents=True)
    records = [read(f) for f in sorted(d.glob("worlds/*/world.json"))]
    train = [
        r
        for r in records
        if r["instance"] < 12 and r["instance"] % 2 == r["permutation"]
    ]
    held = [r for r in records if r["instance"] in (80, 81)]
    assert len(train) == 768 and len(held) == 256
    save(out / "worlds.csv", records)
    rows = []
    for f in sorted(d.glob("worlds/*/free-*.json")):
        for r in read(f):
            r.update(
                split="matrix" if r["instance"] < 90 else "confirmation",
                complete_rate=r["issued"] / r["slots"],
                hit_per_slot=r["valid_draws"] / r["slots"],
                hit_per_issued=r["valid_draws"] / max(1, r["issued"]),
                recall=r["distinct"] / r["gold"],
                accepted_per_issued=r["accepted_full"] / max(1, r["issued"])
                if r["slots"] == 256
                else None,
            )
            rows.append(r)
    assert (
        len([r for r in rows if r["slots"] == 256 and r["arm"] == "A"])
        == (256 + 64) * 3
    )
    fields = ["split", "size", "variant", "arm", "slots"]
    cols = [
        "complete_rate",
        "hit_per_slot",
        "hit_per_issued",
        "recall",
        "distinct",
        "seconds",
    ]
    save(out / "free.csv", pooled(rows, fields, cols))
    save(out / "free-seeds.csv", pooled(rows, fields + ["seed"], cols))
    save(
        out / "native-accept.csv",
        pooled([r for r in rows if r["slots"] == 256], fields, ["accepted_per_issued"]),
    )
    assert len(read(d / "binding.json")) == 36 * 3 * 5
    save(
        out / "binding.csv",
        pooled(
            read(d / "binding.json"),
            ["arm", "seed"],
            ["complete", "first", "second", "join", "guard_given_join"],
        ),
    )
    # Both physical permutations and all fit seeds are repeated observations of
    # the same semantic instance; resample whole instances for uncertainty.
    import numpy as np

    bindings = read(d / "binding.json")
    ids = sorted({r["instance"] for r in bindings})
    draws = np.random.default_rng(411).integers(len(ids), size=(10000, len(ids)))
    contrasts = []
    for arm in "ABC":
        diffs = np.asarray(
            [
                mean(
                    r["complete"]
                    for r in bindings
                    if r["arm"] == arm and r["instance"] == i
                )
                - 1 / 16
                for i in ids
            ]
        )
        lo, hi = np.quantile(diffs[draws].mean(1), [0.025, 0.975])
        contrasts.append(
            dict(
                arm=arm,
                instances=len(ids),
                delta=float(diffs.mean()),
                low95=lo,
                high95=hi,
                better_instances=int((diffs > 0).sum()),
            )
        )
    save(out / "paired-binding.csv", contrasts)
    diag = []
    for r in read(d / "small-fit.json"):
        diag.append(
            dict(
                step=r["step"],
                split=r["split"],
                states=len(r["complete"]),
                mass=mean(r["complete"]),
                first=mean(x[1] for x in r["factors"]),
                second=mean(x[2] for x in r["factors"]),
            )
        )
    save(out / "small-fit.csv", diag)
    curves = []
    weights = []
    for seed in SEEDS:
        evidence = set()
        for arm in "ABC":
            run = read(d / "weights" / str(seed) / f"{arm}.json")
            evidence.add(run["draws_sha256"])
            for c in run["curves"]:
                for n, items, count in zip(SIZES, c["held"], c["by_size"]):
                    for vi, v in enumerate(VARIANTS):
                        g = items[vi * 4 : vi * 4 + 4]
                        curves.append(
                            dict(
                                seed=seed,
                                arm=arm,
                                stage=c["stage"] + 1,
                                steps=c["steps"],
                                exposures=c["exposures"],
                                size=n,
                                variant=v,
                                batches_of_size=count,
                                train_ce=c["train_ce"],
                                held_ce=mean(x["ce"] for x in g),
                                goal_mass=mean(x["mass"] for x in g),
                                recall16_expected=mean(x["recall16"] for x in g),
                            )
                        )
        assert len(evidence) == 1
        for path in sorted((d / "weights" / str(seed)).glob("*.pt")):
            weights.append(
                dict(
                    seed=seed,
                    arm=path.stem,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
    save(out / "learning.csv", curves)
    save(out / "weights.csv", weights)
    early = []
    for f in sorted(d.glob("early-*/*/*/[0-9]*.json")):
        seed, source, case = f.relative_to(d).parts[:3]
        for r in read(f):
            if r["kind"] == "slots" and r["budget"] == 256:
                early.append(
                    dict(
                        seed=int(seed.split("-")[1]),
                        source=source,
                        case=case,
                        run=int(f.stem),
                        draw=r["draw"],
                        arm=r["arm"],
                        owners=r["visible_owners"],
                        ports=r["visible_ports"],
                        gold=r["reference_owners"],
                        slots=r["slots"],
                        issued=r["proposed"],
                        distinct=r["distinct"],
                        ops=r["ops"],
                        accepted=r["native"].get("accepted", 0),
                    )
                )
    assert len(early) == 540
    save(out / "early.csv", early)
    native = []
    facts = {}
    for f in sorted(d.glob("native/*/*/native-address/*/*/run.json")):
        seed = int(f.relative_to(d).parts[1])
        r = read(f)
        native.append(
            dict(
                case=r["case"],
                arm=r["method"],
                seed=seed,
                block=r["block"],
                coverage=100 * r["covered"] / r["reference"],
                covered=r["covered"],
                reference=r["reference"],
                paid=r["paid"],
                effective=r["signed_ops"],
                ept=r["ept"],
                eps=r["cold_eps"],
                seconds=r["cold_wall"],
                stop=r["termination"],
                graph=r["state_sha"],
            )
        )
        key = f"{seed}/{r['case']}/{r['method']}"
        if key in facts and facts[key] != r["facts"]:
            raise ValueError("timing replicates diverged")
        facts[key] = r["facts"]
    assert len(native) == 60
    save(out / "native.csv", native)
    (out / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")
    cols = ["coverage", "ept", "eps", "paid", "seconds", "covered"]
    by_seed = pooled(native, ["case", "arm", "seed"], cols, median)
    save(out / "independent.csv", pooled(by_seed, ["case", "arm"], cols))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dest", type=Path, required=True)
    a = p.parse_args()
    results(a.out, a.dest)
