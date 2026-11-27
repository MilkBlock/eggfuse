"""Export per-seed native metrics, flips, overlap, timing dispersion and raw-artifact digests."""

import csv
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from value_read_eval import flip_stats


def read(path):
    return json.loads(path.read_text())


def table(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def export(root, out):
    out.mkdir(exist_ok=True, parents=True)
    manifest = {}
    pairs = []
    performance = []
    controls = []
    learning = []
    wiring = []
    for scale in ("pilot", "small", "rich"):
        d = root if scale == "pilot" else root / scale
        files = sorted(
            p
            for p in d.iterdir()
            if p.is_file()
            and p.suffix in (".pt", ".json")
            and not p.name.startswith("kv-export")
        )
        manifest[scale] = {
            "gate": read(d / "gate.json"),
            "files": {p.name: sha(p) for p in files},
        }
        for path in sorted(d.glob("[ABC]-*-1680.json")):
            history = read(path)
            exposure = history.get(
                "complete_targets", history.get("weighted_token_exposure")
            )
            arm, seed, _ = path.stem.split("-")
            for ix, ce in enumerate(history["ce60"], 1):
                learning.append(
                    {
                        "scale": scale,
                        "arm": arm,
                        "seed": seed,
                        "update": 60 * ix,
                        "ce": ce,
                        "trainable": history["trainable"],
                        "frozen_sha": history["frozen"],
                        "targets": 60 * ix * exposure // history["updates"],
                    }
                )
        group = defaultdict(list)
        blind = read(d / "blind.json")
        if scale == "rich":
            blind += read(d / "wide/blind.json")
            manifest[scale]["files"]["wide/blind.json"] = sha(d / "wide/blind.json")
        for r in blind:
            group[r["v"], r["step"], r["seed"], r["label"]].append(r)
        for (arm, step, seed, label), rows in group.items():
            if scale == "rich" and label == "factorial" and step == 1680:
                for agree in (False, True):
                    part = [r for r in rows if (r["bits"][1] == r["bits"][2]) == agree]
                    wiring.append(
                        {
                            "arm": arm,
                            "seed": seed,
                            "guards_agree": agree,
                            "states": len(part),
                            "top_correct": sum(r["gold_margin"] > 0 for r in part),
                            "p_pair": mean(r["p_pair"] for r in part),
                        }
                    )
            wins, count = flip_stats(rows)
            pairs.append(
                dict(
                    scale=scale,
                    arm=arm,
                    step=step,
                    seed=seed,
                    subset=label,
                    n_pairs=count,
                    correct_flips=wins,
                    **{
                        k: mean(x[k] for x in rows)
                        for k in ("p_pair", "p_full", "p_bind", "p_template")
                    },
                )
            )
        raw = read(d / "native.json")

        def cell(r):
            return (
                r["label"],
                tuple(r["schema"]),
                tuple(r["bits"]),
                r["pool"],
                r["draw"],
                r["step"],
                r["seed"],
                r["block"],
            )

        index = {(r["v"], cell(r)): r for r in raw}
        ng = defaultdict(list)
        for r in raw:
            ng[r["v"], r["step"], r["seed"], r["label"]].append(r)
        for (arm, step, seed, label), rows in ng.items():
            trials = [r for r in rows if r["block"] == 0]
            eq = []
            spread = []
            for r in trials:
                k = cell(r)
                mate = index[arm, (*k[:-1], 1)]
                assert (
                    mate["facts"],
                    mate["graph"],
                    mate["ops"],
                    mate["stats"],
                    mate["hits"],
                ) == (r["facts"], r["graph"], r["ops"], r["stats"], r["hits"])
                spread.append(abs(mate["wall"] - r["wall"]) / r["wall"])
                a = index["A", k]
                a1 = index["A", (*k[:-1], 1)]
                if a["graph"] == r["graph"] and a["facts"] == r["facts"]:
                    eq.append(
                        (
                            (r["wall"] + mate["wall"]) / (a["wall"] + a1["wall"]),
                            r["ept"] - a["ept"],
                        )
                    )
            performance.append(
                {
                    "scale": scale,
                    "arm": arm,
                    "step": step,
                    "seed": seed,
                    "subset": label,
                    "n": len(trials),
                    "coverage": mean(r["coverage"] for r in trials),
                    "ept": mean(r["ept"] for r in trials),
                    "eps": mean(r["eps"] for r in rows),
                    "paired_spread": median(spread),
                    "ops": mean(r["ops"] for r in trials),
                    "paid": mean(r["stats"]["paid"] for r in trials),
                    "root_slot_hit": sum(r["hits"] for r in trials)
                    / sum(r["slots"] for r in trials),
                    "confirmed": sum(r["stats"]["higher_completed"] for r in trials),
                    "selected": sum(
                        r["stats"].get("higher_selected", 0) for r in trials
                    ),
                    "opened": sum(r["stats"].get("higher_opened", 0) for r in trials),
                    "matched": len(eq),
                    "matched_wall_ratio": median(x for x, y in eq) if eq else None,
                    "matched_ept_delta": mean(y for x, y in eq) if eq else None,
                }
            )
        if scale == "rich":
            for name in ("gradients", "controls", "layouts", "gate", "wiring-audit"):
                shutil.copyfile(d / (name + ".json"), out / (name + ".json"))
            controls.extend(read(d / "controls.json"))
    table(out / "conditional.csv", pairs)
    table(out / "execution.csv", performance)
    cg = defaultdict(list)
    for r in controls:
        cg[r["control"], r["seed"], r["step"], "all"].append(r)
        if r["schema"] == [0, 0, 0]:
            cg[r["control"], r["seed"], r["step"], "first"].append(r)
    sums = []
    for (c, seed, step, subset), rows in cg.items():
        wins, count = flip_stats(rows)
        sums.append(
            {
                "control": c,
                "seed": seed,
                "step": step,
                "subset": subset,
                "pairs": count,
                "wins": wins,
                "p_pair": mean(r["p_pair"] for r in rows),
            }
        )
    table(out / "intervention.csv", sums)
    table(out / "training.csv", learning)
    table(out / "wiring-conditions.csv", wiring)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
