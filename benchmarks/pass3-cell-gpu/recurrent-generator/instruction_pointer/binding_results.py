"""Aggregate by semantic instance; retain fit seeds, raw native outcomes and address pairs."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def save(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def group(rows, keys, fields):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[k] for k in keys)].append(r)
    return [
        dict(
            zip(keys, key),
            **{k: mean(r[k] for r in items) for k in fields},
            observations=len(items),
        )
        for key, items in sorted(groups.items())
    ]


def result(d, out):
    out.mkdir(exist_ok=True, parents=True)
    rows = []
    paired = {}
    inter = []
    folders = [
        p
        for p in (d / "worlds").iterdir()
        if p.name in ("test", "noise", "cross-guard")
        or p.name.startswith(("density-", "subset-"))
    ]
    for folder in folders:
        for world in sorted(folder.iterdir()):
            for seed in (9633, 5003, 1777):
                data = read(world / f"eval-{seed}.json")
                assert len(data) == 6
                for x in data:
                    k = (
                        x["split"],
                        x["size"],
                        x["layout"],
                        x["instance"],
                        x["seed"],
                        x["arm"],
                    )
                    paired.setdefault(k, {})[x["order"]] = np.array(
                        x["second_distribution"]
                    )
                    row = dict(
                        split=x["split"],
                        layout=x["layout"],
                        size=x["size"],
                        domain=x["domain"],
                        arm=x["arm"],
                        seed=seed,
                        instance=x["instance"],
                        order=x["order"],
                        first=x["conditional"][0][0],
                        second=x["conditional"][1][0],
                        second_top1=x["conditional"][1][1],
                        last=x["conditional"][-1][0],
                        full=x["mass"],
                        signed=x["signed"],
                        hits=x["hits"],
                        effective=x["effective"],
                        gold=x["gold"],
                        guard_rejected=x["receipts"]
                        .get("rejected", {})
                        .get("guard", 0),
                        free=x["hits"] / x["signed"],
                        recall1=x["recalls"][0],
                        recall4=x["recalls"][1],
                        recall16=x["recalls"][2],
                        recall32=x["recalls"][3],
                    )
                    rows.append(row)
                    if "unwired" in x:
                        inter.append(
                            dict(
                                arm=x["arm"],
                                seed=seed,
                                normal=row["second"],
                                unwired=x["unwired"][0],
                                raw_i64=x["raw_i64"][0],
                            )
                        )
    assert len(rows) == (624 + 48 + 80 + 24 + 32) * 3 * 6
    metrics = [
        "domain",
        "first",
        "second",
        "second_top1",
        "last",
        "full",
        "free",
        "recall1",
        "recall4",
        "recall16",
        "recall32",
    ]
    save(
        out / "free.csv",
        group(rows, ["split", "layout", "size", "arm", "seed"], metrics),
    )
    core = [r for r in rows if r["split"] == "test" and r["layout"].startswith("eq")]
    save(out / "equality.csv", group(core, ["size", "arm"], metrics))
    curve = group(
        [r for r in rows if r["split"].startswith("density")],
        ["domain", "arm"],
        ["first", "second", "second_top1", "full", "free", "recall32"],
    )
    save(out / "density.csv", curve)
    tv = [
        dict(
            split=k[0],
            size=k[1],
            layout=k[2],
            arm=k[5],
            tv=np.abs(v[0] - v[1]).sum() / 2,
        )
        for k, v in paired.items()
    ]
    save(out / "permutation.csv", group(tv, ["split", "layout", "size", "arm"], ["tv"]))
    save(
        out / "cross-guard.csv",
        group(
            [r for r in rows if r["split"] == "cross-guard"],
            ["arm"],
            ["first", "second", "full", "hits", "signed", "guard_rejected"],
        ),
    )
    save(
        out / "query.csv",
        group(
            read(d / "query-probe.json"),
            ["arm", "intervention", "path"],
            ["delta_log_odds", "before", "after", "delta_query", "delta_key"],
        ),
    )
    corpus = []
    for split in [d / "worlds/train", *sorted(folders)]:
        docs = [read(p) for p in split.glob("*/ok.json")]
        corpus.append(
            dict(
                split=split.name,
                snapshots=len(docs),
                layouts=len({s["layout"] for s in docs}),
                native_new_targets=sum(len(s["gold"]) for s in docs),
                nonempty_warm_prefix=sum(bool(s["warm"]) for s in docs),
            )
        )
    save(out / "corpus.csv", corpus)
    save(
        out / "wire-controls.csv",
        group(inter, ["arm", "seed"], ["normal", "unwired", "raw_i64"]),
    )
    save(
        out / "causal.csv",
        group(
            read(d / "interventions.json"),
            ["arm", "seed"],
            [
                "left",
                "right",
                "right_before",
                "only_wiring",
                "field_transplant",
                "unrelated",
                "both_argmax",
                "query_change",
                "whole_key_change",
            ],
        ),
    )
    save(
        out / "conditional.csv",
        group(
            read(d / "conditional.json"),
            ["arm", "changed"],
            ["targets", "physical", "hits", "draws", "effective"],
        ),
    )
    eg = read(d / "egg-prefix.json")
    save(
        out / "egg-prefix.csv",
        group(
            [dict(r, connected=int(r["wires"] > 0)) for r in eg["rows"]],
            ["case", "source", "connected", "seed", "arm"],
            ["domain", "second_mass", "top1", "uniform"],
        ),
    )
    save(
        out / "sparse.csv",
        group(
            [
                dict(
                    r,
                    sparse=r["metrics"][0],
                    dense=r["metrics"][1],
                    reads=r["metrics"][2],
                )
                for r in read(d / "sparse.json")
            ],
            ["size", "arm"],
            ["sparse", "dense", "reads"],
        ),
    )
    save(out / "synthetic-online.csv", read(d / "online.json"))
    trials = []
    facts = {}
    for p in sorted(d.glob("egg-online/*/*/result.json")):
        r = read(p)
        key = f"{p.parents[1].name}/{r['seed']}/{r['arm']}"
        if key in facts:
            assert facts[key] == r["facts"]
        facts[key] = r.pop("facts")
        trials.append(
            dict(
                case=p.parents[1].name,
                arm=r["arm"],
                seed=r["seed"],
                block=r["block"],
                covered=r["covered"],
                coverage=r["covered"] / r["reference"],
                reference=r["reference"],
                ept=r["ept"],
                eps=r["eps"],
                ops=r["ops"],
                wall=r["wall"],
                graph=r["graph"],
                **{
                    k: r["stats"].get(k, 0)
                    for k in (
                        "attempts",
                        "paid",
                        "parent_candidate_scores",
                        "empty_domain",
                    )
                },
            )
        )
    assert len(trials) == 36
    save(out / "egg-independent.csv", trials)
    (out / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")
    curves = []
    weights = []
    for p in sorted((d / "weights").glob("*/*.json")):
        curves.extend(dict(seed=int(p.parent.name), arm=p.stem, **r) for r in read(p))
        weights.append(
            dict(
                seed=int(p.parent.name),
                arm=p.stem,
                sha256=hashlib.sha256(p.with_suffix(".pt").read_bytes()).hexdigest(),
            )
        )
    save(out / "training.csv", curves)
    save(out / "weights.csv", weights)
    for file in ["parity.json", "precision.json"]:
        (out / file).write_bytes((d / file).read_bytes())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dest", type=Path, required=True)
    a = p.parse_args()
    result(a.out, a.dest)
