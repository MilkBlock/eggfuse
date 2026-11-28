"""Check asynchronous metrics against saved native trajectories and retain unsaved checks."""

import csv
import json
import os
from pathlib import Path

from learning_dashboard import GROUPS
from learning_entropy import REPORT, table


def run():
    art = Path(os.environ["PARTNER_INDEX_OUT"])
    con = art / "continuation-exposure"
    start = json.loads(
        (art / "full-ce-scaling/fits/local-s71-t100000.json").read_text()
    )
    checks = []
    fits = []
    for group, stem in GROUPS.items():
        if group in ("matched-end-to-end", "A-batched"):
            continue
        directory = con / group
        for path in sorted(directory.glob(stem + "-t*.json")):
            d = json.loads(path.read_text())
            fits.append(
                {
                    k: d[k]
                    for k in (
                        "registered",
                        "forward_observed",
                        "connected",
                        "states",
                        "targets",
                        "exposures",
                        "steps",
                        "seconds",
                        "train_ce",
                    )
                }
            )
            f = fits[-1]
            f.update(
                group=group,
                added_exposures=d["exposures"] - 100000,
                added_seconds=d["seconds"] - start["seconds"],
            )
            f["added_tokens_s"] = f["added_exposures"] / f["added_seconds"]
        for line in (directory / (stem + "-live.jsonl")).read_text().splitlines():
            rec = json.loads(line)
            metrics = rec.get("metrics", {})
            assert not metrics.get("native_256/check_failed")
            if not any(k.startswith("native_256") for k in metrics):
                continue
            point = rec["step"]
            path = REPORT / f"native-{group}_{stem}-t{point}.csv"
            for seed in (193, 307):
                pre = f"native_256/loopfact_g{seed}_"
                row = {
                    "group": group,
                    "exposure": point,
                    "seed": seed,
                    **{
                        k: metrics[pre + k]
                        for k in ("coverage", "ept", "eps", "continuation_ept", "paid")
                    },
                }
                if path.exists():
                    with path.open() as fp:
                        independent = next(
                            r
                            for r in csv.DictReader(fp)
                            if (r["case"], r["seed"], r["cap"])
                            == ("loopfact", str(seed), "256")
                        )
                    assert all(
                        abs(float(independent[k]) - row[k]) < 1e-9
                        for k in ("coverage", "paid", "ept", "continuation_ept")
                    ), row
                    row["saved_checkpoint_match"] = True
                else:
                    row["saved_checkpoint_match"] = None
                checks.append(row)
        first_tracked = 130000 if group.startswith("read-width-") else 250000
        last = max(r["exposures"] for r in fits if r["group"] == group)
        for seed in (193, 307):
            actual = sorted(
                r["exposure"] // 10000
                for r in checks
                if r["group"] == group and r["seed"] == seed
            )
            assert actual == list(
                range(first_tracked // 10000 + 1, last // 10000 + 1)
            ), (group, seed, actual)
    table("parallel-fits.csv", fits)
    table("parallel-live-native.csv", checks)


if __name__ == "__main__":
    run()
