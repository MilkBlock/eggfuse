"""Summarize native graph pairs separately from offline routing interventions."""

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from operand_read_probe import write


def groups(rows, keys):
    table = defaultdict(list)
    for r in rows:
        table[tuple(r[k] for k in keys)].append(r)
    return table


def read_csv(p):
    with p.open() as f:
        return list(csv.DictReader(f))


def export(src, out):
    out.mkdir(exist_ok=True, parents=True)
    learning = []
    native = []
    effects = []
    for label in ("known", "new_wire", "width", "shift", "deep", "mixed"):
        d = json.loads((src / f"{label}-diag.json").read_text())
        for (arm, seed, layout), rows in groups(d, ("arm", "seed", "layout")).items():
            pairs = defaultdict(list)
            for r in rows:
                bits = r["bits"][:2] if label == "new_wire" else r["bits"]
                pairs[r["pool"], r["g"], r["o"], tuple(bits)].append(r)
            conflicts = []
            if label != "mixed":
                for pair in pairs.values():
                    assert len(pair) == 2
                    if pair[0]["gold"] != pair[1]["gold"]:
                        conflicts.append(pair)
            learning.append(
                {
                    "label": label,
                    "arm": arm,
                    "seed": seed,
                    "layout": layout,
                    "states": len(rows),
                    "pairs": len(conflicts),
                    "flips": sum(all(r["correct"] for r in p) for p in conflicts)
                    if conflicts
                    else None,
                    "max_tv": max(r["tv"] for r in rows),
                    "mean_tv": mean(r["tv"] for r in rows),
                    "max_probability_delta": max(r["max_delta"] for r in rows),
                    "mean_verified_mass": mean(r["valid_mass"] for r in rows),
                    "p_full": mean(r["p_full"] for r in rows)
                    if label != "mixed"
                    else None,
                    "mean_read_mass": mean(r["read_mass"] for r in rows)
                    if "read_mass" in rows[0]
                    else None,
                }
            )
            if "grads" in rows[0]:
                effects.append(
                    dict(
                        label=label,
                        arm=arm,
                        seed=seed,
                        layout=layout,
                        **{
                            k: mean(r["grads"][i] for r in rows)
                            for i, k in enumerate(
                                (
                                    "operand_q",
                                    "field_k",
                                    "field_v",
                                    "relation",
                                    "input_role_weight",
                                    "query_weight",
                                )
                            )
                        },
                    )
                )
        raw = json.loads((src / f"{label}-live.json").read_text())
        ix = {
            (
                r["arm"],
                r["seed"],
                r["pool"],
                r["g"],
                r["o"],
                tuple(r["bits"]),
                r["wire"],
                r["draw"],
                r["block"],
            ): r
            for r in raw
        }
        for (arm, seed), rows in groups(raw, ("arm", "seed")).items():
            cases = [r for r in rows if r["block"] == 0]
            matched = []
            spreads = []
            for r in cases:
                k = (
                    seed,
                    r["pool"],
                    r["g"],
                    r["o"],
                    tuple(r["bits"]),
                    r["wire"],
                    r["draw"],
                )
                other = ix[arm, *k, 1]
                a = ix["A", *k, 0]
                assert all(
                    r[n] == other[n]
                    for n in ("graph", "facts", "receipts", "stats", "valid", "ops")
                )
                spreads.append(abs(other["wall"] - r["wall"]) / r["wall"])
                if (a["graph"], a["facts"]) == (r["graph"], r["facts"]):
                    matched.append(
                        (r["wall"] + other["wall"])
                        / (a["wall"] + ix["A", *k, 1]["wall"])
                    )
            native.append(
                {
                    "label": label,
                    "arm": arm,
                    "seed": seed,
                    "cases": len(cases),
                    "coverage": mean(r["coverage"] for r in cases),
                    "ept": mean(r["ept"] for r in cases),
                    "eps": mean(r["eps"] for r in rows),
                    "paid": mean(r["stats"]["paid"] for r in cases),
                    "first_page_distinct": mean(r["valid"] for r in cases),
                    "completed": mean(r["stats"]["higher_completed"] for r in cases),
                    "type_rejections": mean(
                        r["receipts"]["rejected"].get("type", 0) for r in cases
                    ),
                    "matched": len(matched),
                    "same_graph_wall_ratio": median(matched) if matched else None,
                    "pair_spread": median(spreads),
                }
            )
    write(out / "layout.csv", learning)
    write(out / "native.csv", native)
    write(out / "gradients.csv", effects)
    controls = read_csv(src / "controls.csv")
    write(
        out / "controls.csv",
        [
            {
                "seed": s,
                "mode": m,
                "n": len(r),
                "both": sum(x["both"] == "True" for x in r),
                "neither": sum(x["neither"] == "True" for x in r),
            }
            for (s, m), r in groups(controls, ("seed", "mode")).items()
        ],
    )
    rolls = read_csv(src / "rollout-pairs.csv")
    write(
        out / "rollout-pairs.csv",
        [
            dict(
                arm=a,
                n=len(r),
                **{
                    k: sum(x[k] == "True" for x in r)
                    for k in ("facts", "graph", "requests", "ops")
                },
            )
            for (a,), r in groups(rolls, ("arm",)).items()
        ],
    )
    mixed = read_csv(src / "mixed-probability.csv")
    write(
        out / "mixed.csv",
        [
            dict(
                arm=a,
                seed=s,
                **{
                    k: mean(float(x[k]) for x in r)
                    for k in (
                        "higher_mass",
                        "valid_higher",
                        "valid_ref_given_higher",
                        "distinct_valid_at_six",
                        "valid_tokens",
                        "top_token",
                        "valid_total",
                    )
                },
            )
            for (a, s), r in groups(mixed, ("arm", "seed")).items()
        ],
    )
    transfer = json.loads((src / "transfer-test-native.json").read_text())
    summary = []
    diagnostics = json.loads((src / "transfer-test-diag.json").read_text())
    for (label, mode, seed), rows in groups(
        transfer, ("label", "mode", "seed")
    ).items():
        cases = [r for r in rows if r["block"] == 0]
        for pair in groups(rows, ("case", "wire", "draw")).values():
            assert len(pair) == 2 and all(
                pair[0][k] == pair[1][k] for k in ("facts", "graph", "stats", "ops")
            )
        ds = [
            r
            for r in diagnostics
            if (r["label"], r["mode"], r["seed"]) == (label, mode, seed)
        ]
        summary.append(
            {
                "label": label,
                "mode": mode,
                "seed": seed,
                "n": len(cases),
                "coverage": mean(r["coverage"] for r in cases),
                "ept": mean(r["ept"] for r in cases),
                "eps": mean(r["eps"] for r in rows),
                "complete": mean(r["stats"]["higher_completed"] for r in cases),
                "type_fail": mean(
                    r["receipts"]["rejected"].get("type", 0) for r in cases
                ),
                "first_verified_mass": mean(r["valid_mass"] for r in ds),
            }
        )
    write(out / "transfer.csv", summary)
    (out / "checkpoints.csv").write_bytes((src / "checkpoints.csv").read_bytes())
    files = list(src.glob("*.pt")) + list(src.glob("*.json")) + list(src.glob("*.csv"))
    manifest = {}
    for p in sorted(
        files + [src.parent / "operand-read" / f"D-{s}-1680.pt" for s in (71, 113)]
    ):
        with p.open("rb") as f:
            manifest[str(p.relative_to(src.parent))] = hashlib.file_digest(
                f, "sha256"
            ).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
