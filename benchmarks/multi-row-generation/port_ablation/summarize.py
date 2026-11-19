"""Create per-family and per-seed tables. Do not pool seeds as independent graphs."""

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median

import numpy as np

HERE = Path(__file__).resolve().parent
FIELDS = (
    "nonempty_complete_graphs",
    "nonempty_graphs",
    "wrong_live_parent",
    "wrong_live_parent_same_payload",
    "wrong_live_parent_with_correct_parent_available",
    "absent_parent_reference",
    "illegal_producer_binding",
    "duplicates",
    "missing",
    "illegal",
    "obligations",
    "active_outputs",
    "valid_bindings",
    "request_has_no_source_match",
    "unavailable_parent_obligations",
    "parent_ready_nonempty_graphs",
    "parent_ready_nonempty_complete_graphs",
    "probe_wrong_twin",
)


def sum_fields(values):
    return {k: sum(v.get(k, 0) for v in values) for k in FIELDS}


def record(result, templates, name, subset, split):
    arm, seed = name.rsplit("-", 1)
    reports = [result["panels"][f"{t['id']}/{split}"][name] for t in templates]
    counts = sum_fields([p["run2"] for p in reports])
    row = dict(
        arm=arm,
        seed=int(seed),
        subset=subset,
        split=split,
        templates=len(templates),
        families=len(set(t["family_id"] for t in templates)),
        **counts,
    )
    consistent = [p["consistent"] for p in reports]
    for k in (
        "graphs",
        "complete",
        "wrong_live_parent",
        "duplicates",
        "missing",
        "illegal",
        "obligations",
    ):
        row["snapshot_" + k] = sum(v[k] for v in consistent)
    row["complete_pairs"] = sum((p["complete_twin_pairs"] or 0) for p in reports)
    fam_counts = {}
    for t, p in zip(templates, reports):
        v = fam_counts.setdefault(t["family_id"], [0, 0])
        v[0] += p["run2"]["nonempty_complete_graphs"]
        v[1] += p["run2"]["nonempty_graphs"]
    row["family_macro_complete_rate"] = round(mean(k / n for k, n in fam_counts.values() if n), 5)
    row["first_complete"] = sum(p["run1"]["complete_graphs"] for p in reports)
    row["graphs"] = sum(p["run1"]["graphs"] for p in reports)
    for kind in ("cached", "cold"):
        if split == "collision" and all(t["id"] in result["timings"] for t in templates):
            timed = [result["timings"][t["id"]][kind][name] for t in templates]
            samples = [v for panel in timed for v in panel["samples_ms"]]
            row[kind + "_ms"] = round(median(samples), 4)
            row[kind + "_nonempty_exact_per_second"] = round(
                1000 * sum(p["complete"] for p in timed) / sum(samples), 5
            )
        else:
            row[kind + "_ms"] = "NA"
            row[kind + "_nonempty_exact_per_second"] = "NA"
    return row


def write_tsv(path, rows):
    with path.open("w") as stream:
        out = csv.DictWriter(stream, list(rows[0]), delimiter="\t", lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def flips(result, templates, first, second):
    # Resample whole counterfactual pairs within fixed templates; the two families
    # are not a random sample sufficiently large for population-level intervals.
    blocks = []
    won = lost = 0
    for t in templates:
        panel = result["panels"][t["id"] + "/collision"]
        before = np.asarray(panel[first]["complete_by_graph"])
        after = np.asarray(panel[second]["complete_by_graph"])
        assert np.all(panel[first]["nonempty_by_graph"]) and np.all(
            panel[second]["nonempty_by_graph"]
        )
        diff = after - before
        won += int((diff == 1).sum())
        lost += int((diff == -1).sum())
        blocks.append(diff.reshape(-1, 2).sum(-1))
    rng = np.random.default_rng(435199)
    changes = sum(b[rng.integers(len(b), size=(4000, len(b)))].sum(1) for b in blocks)
    lo, hi = np.percentile(changes, [2.5, 97.5])
    return dict(
        before=first,
        after=second,
        gained_graphs=won,
        lost_graphs=lost,
        delta=won - lost,
        conditional_pair_bootstrap_delta_low=round(float(lo), 2),
        conditional_pair_bootstrap_delta_high=round(float(hi), 2),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    r = json.loads(a.report.read_text())
    ts = json.loads((HERE / "corpus/manifest.json").read_text())["templates"]
    held = [t for t in ts if t["split"] == "heldout"]
    train = [t for t in ts if t["split"] == "train"]
    groups = {
        "heldout_all": held,
        "heldout_warm": [t for t in held if all(t["atomic_seen_in_training"])],
        "heldout_cold": [t for t in held if not all(t["atomic_seen_in_training"])],
        "train_families": train,
    }
    groups.update(
        {
            f: [t for t in held if t["family_id"] == f]
            for f in sorted({t["family_id"] for t in held})
        }
    )
    groups.update({t["id"]: [t] for t in held})
    rows = [
        record(r, templates, name, k, split)
        for k, templates in groups.items()
        for split in ("iid", "collision")
        for name in r["fits"]
    ]
    write_tsv(a.output / "metrics.tsv", rows)
    pairs = []
    for seed in (1703, 1709):
        ref = f"shared_roles-{seed}"
        for name in r["fits"]:
            if name != ref and name.endswith(str(seed)):
                pairs.append(flips(r, held, ref, name))
    write_tsv(a.output / "paired.tsv", pairs)
    print("heldout_all, collision")
    for v in rows:
        if v["subset"] == "heldout_all" and v["split"] == "collision":
            print(
                v["arm"],
                v["seed"],
                *[
                    v[k]
                    for k in (
                        "nonempty_complete_graphs",
                        "nonempty_graphs",
                        "wrong_live_parent",
                        "duplicates",
                        "missing",
                        "cached_ms",
                        "cold_ms",
                    )
                ],
            )


if __name__ == "__main__":
    main()
