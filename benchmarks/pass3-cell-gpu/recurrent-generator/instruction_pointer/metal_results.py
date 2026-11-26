"""Collect fits and complete paired native runs, retaining actual covered sets and replay digests."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_text())


def write_csv(path, rows):
    with path.open("w") as file:
        writer = csv.DictWriter(file, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(out, target):
    fits, curves, runs, totals = [], [], [], []
    for budget, root in ((192, out), (768, out / "long")):
        for path in sorted(root.glob("*/fit.json")):
            fit = read(path)
            assert fit["updates"] == budget
            row = {
                "updates": budget,
                "size": fit["size"],
                "data": fit["data"],
                "parameters": sum(fit[k]["parameters"] for k in ("mark", "rate")),
                "weights_sha256": fit["sha256"],
            }
            for kind in ("mark", "rate"):
                row[kind + "_train_seconds"] = fit[kind]["seconds"]
                for point in fit[kind]["curve"]:
                    for split in ("train", "held"):
                        curves.append(
                            dict(
                                updates=budget,
                                size=fit["size"],
                                data=fit["data"],
                                module=kind,
                                step=point["step"],
                                split=split,
                                **point[split],
                            )
                        )
            fits.append(row)
        for path in sorted(root.glob("*/*-b*.json")):
            r = read(path)
            series = path.name.split("-", 1)[0]
            if series not in {"paired", "gnn"}:
                series = "grid"
            runs.append(
                dict(
                    updates=budget,
                    series=series,
                    **r,
                )
            )
    groups = defaultdict(list)
    for run in runs:
        key = (
            run["updates"],
            run["series"],
            run["size"],
            run["dataset"],
            run["device"],
            run["case"],
        )
        groups[key].append(run)
    for key, pair in groups.items():
        if len(pair) != 2 or {v["block"] for v in pair} != {0, 1}:
            raise ValueError(("missing paired runs", key))
        r = pair[0]
        eq = len({v["state_sha"] for v in pair}) == 1
        row = dict(zip(("updates", "series", "size", "dataset", "device", "case"), key))
        row.update(
            same_endpoint=eq,
            covered=r["covered"],
            reference=r["reference"],
            coverage=r["covered"] / r["reference"],
            paid=r["paid"],
            signed_ops=r["signed_ops"],
            ept=r["ept"],
            cold_eps=median(v["cold_eps"] for v in pair),
            wall_min=min(v["cold_wall"] for v in pair),
            wall_max=max(v["cold_wall"] for v in pair),
            cold_wall=median(v["cold_wall"] for v in pair),
            state_sha=r["state_sha"],
            address_calls=r["inference"].get("mark_calls", 0),
            rate_calls=r["inference"].get("rate_calls", 0),
            probes=sum(r["work"].get(k, 0) for k in ("template_probe", "port_probe")),
            synchronous_module_seconds=median(
                sum(t for k, t in v["inference"].items() if k.endswith("_seconds"))
                for v in pair
            ),
        )
        totals.append(row)
    if len(fits) != 13 or len(runs) != 152 or len(groups) != 76:
        raise ValueError(("incomplete grid", len(fits), len(runs), len(groups)))
    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / "models.csv", fits)
    write_csv(target / "learning.csv", curves)
    write_csv(target / "rollouts.csv", totals)
    (target / "runs.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in runs)
    )
    (target / "datasets.json").write_text(
        json.dumps(
            {k: read(out / (k + ".json")) for k in ("small", "large", "held")}, indent=2
        )
        + "\n"
    )
    (target / "dispatch.csv").write_text((out / "dispatch.csv").read_text())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    summarize(args.out, args.destination)
