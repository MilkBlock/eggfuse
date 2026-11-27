"""Export auditable observations, timing-matched comparisons and weight hashes."""

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path
from statistics import mean, median

import torch

from token_embedding_study import SEEDS, UPDATES, VARIANTS


def read(path):
    return json.loads(path.read_text())


def table(path, rows):
    with path.open("w") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(source, out):
    out.mkdir(exist_ok=True, parents=True)
    for name in (
        "trace",
        "layouts",
        "native",
        "prob",
        "before-native",
        "before-prob",
        "interventions",
        "guard-probe",
        "owner",
        "instances",
    ):
        shutil.copyfile(source / f"{name}.json", out / f"{name}.json")
    corpus = torch.load(source / "training.pt", weights_only=False)

    def fid(s):
        return (
            s["run"],
            s["epoch"],
            tuple(s["menu"]),
            tuple(s["response"]),
            tuple(s["ports"]),
        )

    state_set = {(n, fid(s)) for n, records in corpus.items() for s, _ in records}
    targets = {
        (n, fid(s), t) for n, records in corpus.items() for s, ts in records for t in ts
    }
    manifest = {
        "programs": len(corpus),
        "records": sum(len(r) for r in corpus.values()),
        "states": len(state_set),
        "state_targets": len(targets),
        "updates": UPDATES,
        "exposures": 6 * UPDATES,
        "weights": {},
    }
    grads = []
    for seed in SEEDS:
        for v in VARIANTS:
            name = f"{v}-{seed}"
            m = read(source / (name + ".json"))
            manifest["weights"][name] = dict(
                sha256=hashlib.sha256(
                    (source / (name + ".pt")).read_bytes()
                ).hexdigest(),
                **{
                    k: m[k]
                    for k in ("frozen_sha256", "registered", "trainable", "ce60")
                },
            )
            for k, d in m["groups"].items():
                grads.append(dict(v=v, seed=seed, group=k, **d))
    assert len({m["frozen_sha256"] for m in manifest["weights"].values()}) == 1
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    table(out / "gradients.csv", grads)
    summary = []
    matched = []
    for when, prefix in [("before", "before-"), ("after", "")]:
        native = read(source / f"{prefix}native.json")
        probs = read(source / f"{prefix}prob.json")
        index = {
            (r["v"], r["case"], r["seed"], r["draw"], r["block"]): r for r in native
        }
        for v in VARIANTS:
            rows = [r for r in native if r["v"] == v]
            base = [r for r in rows if not r["block"]]
            for r in base:
                other = index[v, r["case"], r["seed"], r["draw"], 1]
                assert all(other[k] == r[k] for k in ("facts", "graph", "stats", "ops"))
            prob = [
                r
                for r in probs
                if r["v"] == v and r["case"].split("-")[1] in ("0", "1")
            ]
            equal = [
                (r, index["current", r["case"], r["seed"], r["draw"], r["block"]])
                for r in rows
            ]
            equal = [
                (r, b)
                for r, b in equal
                if r["graph"] == b["graph"] and r["facts"] == b["facts"]
            ]
            if equal:
                matched.append(
                    {
                        "when": when,
                        "v": v,
                        "trajectories": len(equal) // 2,
                        "mean_ept_diff": mean(r["ept"] - b["ept"] for r, b in equal),
                        "median_wall_ratio": median(
                            r["wall"] / b["wall"] for r, b in equal
                        ),
                    }
                )
            summary.append(
                dict(
                    when=when,
                    v=v,
                    n=len(base),
                    **{
                        k: mean(r[k] for r in rows)
                        for k in ("coverage", "ept", "eps", "wall")
                    },
                    coverage_seed="/".join(
                        f"{mean(r['coverage'] for r in base if r['seed'] == seed):.5f}"
                        for seed in sorted({r["seed"] for r in base})
                    ),
                    median_paired_wall_spread=median(
                        abs(
                            r["wall"]
                            - index[v, r["case"], r["seed"], r["draw"], 1]["wall"]
                        )
                        / r["wall"]
                        for r in base
                    ),
                    full_graph=sum(r["reference_graph"] for r in base),
                    **{
                        k: sum(r["stats"].get(k, 0) for r in base)
                        for k in (
                            "higher_selected",
                            "higher_opened",
                            "higher_completed",
                            "accepted_consumer_of_higher",
                        )
                    },
                    **{
                        k: mean(p[k] for p in prob)
                        for k in (
                            "correct_vs_other",
                            "p_bind",
                            "p_complete",
                            "structure_distance",
                        )
                    },
                    permutation_max=max(p["perm_error"] for p in probs if p["v"] == v),
                )
            )
    table(out / "summary.csv", summary)
    table(out / "matched.csv", matched)


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
