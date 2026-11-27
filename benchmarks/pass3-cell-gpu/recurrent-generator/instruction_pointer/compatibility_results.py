"""Report conditional pair flips separately from marginal native performance."""

import csv
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from statistics import mean, median

import numpy as np
import torch

from compatibility_study import ARMS, SEEDS, baseline_path


def read(path):
    return json.loads(path.read_text())


def table(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rate(rows, k):
    return sum(r[k] for r in rows) / sum(r["slots"] for r in rows)


def pair_stats(rows):
    assert len(rows) % 2 == 0
    pairs = list(zip(rows[::2], rows[1::2], strict=True))
    for a, b in pairs:
        assert (
            a["flip"] == 0
            and b["flip"] == 1
            and a["seed"] == b["seed"]
            and a.get("case", a.get("pair")) == b.get("case", b.get("pair"))
        )
    out = {
        "pairs": len(pairs),
        "p_gold": mean(x["template"][x["flip"]] for x in rows),
        "p_pair": mean(x["p_gold_vs_other"] for x in rows),
        "p_bind": mean(x["bind"][x["flip"]] for x in rows),
        "p_token": mean(x["complete"][x["flip"]] for x in rows),
        "structure_l2": mean(x["structure_distance"] for x in rows),
        "key_shift": mean(b["input_key_change"] for a, b in pairs),
    }
    for k in (
        "margin",
        "full_margin",
        "qk_margin",
        "local_margin",
        "global_margin",
        "hint_margin",
        "shared_margin",
    ):
        out[k + "_correct_flips"] = sum(a[k] > 0 > b[k] for a, b in pairs)
        out[k + "_any_flips"] = sum(a[k] * b[k] < 0 for a, b in pairs)
        out[k + "_abs_change"] = mean(abs(a[k] - b[k]) for a, b in pairs)
    out["attention_abs_change"] = mean(
        abs(a["attention"][t] - b["attention"][t]) for a, b in pairs for t in (0, 1)
    )
    clustered = {}
    for r in rows:
        clustered.setdefault(r.get("case", r.get("pair")), []).append(
            r["p_gold_vs_other"]
        )
    sample = np.array([mean(v) for v in clustered.values()])
    draws = np.random.default_rng(47).choice(sample, (2000, len(sample))).mean(1)
    out["input_pairs"] = len(sample)
    out["p_pair_boot_lo"], out["p_pair_boot_hi"] = np.quantile(draws, [0.025, 0.975])
    out["mean_target_attention"] = mean(v for r in rows for v in r["attention"])
    out["shared_query_margin_difference"] = mean(
        abs(r["margin"] - r["shared_margin"]) for r in rows
    )
    return out


def export(src, out):
    out.mkdir(parents=True, exist_ok=True)
    files = (
        "probes",
        "native",
        "generalization",
        "pairs",
        "address",
        "controls",
        "publish",
        "publish-probes",
        "score-probe",
    )
    for f in files:
        shutil.copyfile(src / f"{f}.json", out / f"{f}.json")
    raw = read(src / "native.json")
    rawidx = {
        (r["arm"], r["seed"], r["case"], r["flip"], r["draw"], r["block"]): r
        for r in raw
    }
    execs = []
    matched = []
    stats = []
    for arm in ARMS:
        for subset in ("all", "seen", "new"):
            rows = [
                r
                for r in raw
                if r["arm"] == arm and (subset == "all" or r["case"].startswith(subset))
            ]
            base = [r for r in rows if r["block"] == 0]
            spread = []
            ratios = []
            ediff = []
            for r in base:
                key = (r["case"], r["flip"], r["draw"])
                rep = rawidx[(arm, r["seed"], *key, 1)]
                assert all(
                    rep[k] == r[k]
                    for k in ("stats", "graph", "ops", "facts", "correct", "tokens")
                )
                spread.append(abs(rep["wall"] - r["wall"]) / r["wall"])
                frozen = rawidx[("A", SEEDS[0], *key, 0)]
                if r["facts"] == frozen["facts"] and r["graph"] == frozen["graph"]:
                    ratios.append(
                        (r["wall"] + rep["wall"])
                        / (frozen["wall"] + rawidx[("A", SEEDS[0], *key, 1)]["wall"])
                    )
                    ediff.append(r["ept"] - frozen["ept"])
            matched.append(
                {
                    "arm": arm,
                    "subset": subset,
                    "equal_graph_pairs": len(ratios),
                    "total": len(base),
                    "median_wall_ratio": median(ratios) if ratios else None,
                    "mean_ept_change": mean(ediff) if ediff else None,
                }
            )
            execs.append(
                {
                    "arm": arm,
                    "subset": subset,
                    "trajectories": len(base),
                    "coverage": mean(r["coverage"] for r in base),
                    "ept": mean(r["ept"] for r in base),
                    "eps": mean(r["eps"] for r in rows),
                    "paired_spread": median(spread),
                    "mean_ops": mean(r["ops"] for r in base),
                    "mean_facts": mean(r["covered"] for r in base),
                    "reference_graphs": sum(r["reference_graph"] for r in base),
                    "mean_paid": mean(r["stats"]["paid"] for r in base),
                    "root_target_hits": rate(base, "correct"),
                    "root_verified_hits": rate(base, "any_valid"),
                    "higher_selected": sum(
                        r["stats"].get("higher_selected", 0) for r in base
                    ),
                    "higher_opened": sum(
                        r["stats"].get("higher_opened", 0) for r in base
                    ),
                    "higher_completed": sum(
                        r["stats"]["higher_completed"] for r in base
                    ),
                }
            )
    table(out / "execution.csv", execs)
    table(out / "matched.csv", matched)
    for file in ("probes", "generalization", "publish-probes"):
        data = read(src / f"{file}.json")
        for arm in dict.fromkeys(x["arm"] for x in data):
            group = {}
            for r in data:
                if r["arm"] != arm:
                    continue
                if file == "publish-probes":
                    k = "published-zero" if r["zero"] else "published-addressed"
                else:
                    name = r["case"]
                    n = int(name.split("-")[-1])
                    if name.startswith("extra"):
                        k = name.rsplit("-", 1)[0]
                    elif name.startswith("fit"):
                        k = "fit-single" if n % 3 == 0 else "fit-multi"
                    else:
                        k = name.split("-")[0] + ("-single" if n % 3 == 0 else "-multi")
                group.setdefault(k, []).append(r)
                if r.get("case") == "fit-0":
                    group.setdefault("memorized-pair", []).append(r)
            for k, rs in group.items():
                stats.append(dict(arm=arm, subset=k, **pair_stats(rs)))
    table(out / "conditional.csv", stats)
    data = torch.load(src / "training.pt", weights_only=False)
    weights = {}
    for f in sorted(src.glob("*.pt")):
        if f.name == "training.pt":
            continue
        weights[f.name] = {
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "training": read(f.with_suffix(".json"))
            if f.with_suffix(".json").exists()
            else "one-pair CE capacity diagnostic",
        }
    seeds = {}
    for path in (src / "worlds").glob("*/world.egg"):
        name = path.parent.name
        split = (
            "fit"
            if name.startswith("fit-")
            else "publish"
            if name.startswith("publish-")
            else "test"
        )
        values = {
            int(v)
            for match in re.finditer(
                r"^\(Seed (\d+) (\d+)\)$", path.read_text(), re.MULTILINE
            )
            for v in match.groups()
        }
        seeds.setdefault(split, set()).update(values - {0})
    assert seeds["fit"].isdisjoint(seeds["test"])
    init_path = baseline_path(os.environ.get("ARTIFACT_ROOT", src.parent))
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "initial_file": init_path.name,
                "initial_sha256": hashlib.sha256(init_path.read_bytes()).hexdigest(),
                "nonzero_seed_values": {k: len(v) for k, v in seeds.items()},
                "worlds": len(data),
                "records": sum(map(len, data.values())),
                "verified_targets": sum(
                    len(ts) for rows in data.values() for _, ts in rows
                ),
                "weights": weights,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
