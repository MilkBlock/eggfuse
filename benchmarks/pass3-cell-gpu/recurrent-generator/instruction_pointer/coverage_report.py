"""Aggregate recurring physical draws by state first, then average over paired seeds."""

import argparse
import csv
import hashlib
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from coverage_fit import ARMS, BUDGETS, SEEDS
from discovery_score import write_csv
from query_fit import read as training_packet
from recursive_train import read


def rows(path):
    with path.open() as f:
        yield from csv.DictReader(f)


def training_results(root, dest):
    totals = Counter()
    for row in rows(root / "fit-check.csv"):
        totals[row["arm"], int(row["budget"])] += int(row["known_productive"]) / 2
    write_csv(
        dest / "train-fit.csv",
        [
            {"arm": arm, "budget": b, "discovered": n}
            for (arm, b), n in sorted(totals.items())
        ],
    )
    shutil.copyfile(root.parent / "calibration.csv", dest / "calibration.csv")
    failures = []
    for f in sorted((root.parent / "failures").glob("*/receipts.json")):
        native = read(f)
        count = Counter()
        for kind, rule, n in native["counts"]:
            count[kind] += n
            if kind == "binding" and rule == 575:
                count["binding575"] += n
        packets = sorted(f.parent.glob("page-*.pkl.gz"))
        used = Counter()
        for pkt in packets:
            s = training_packet(pkt)
            for kind, (rule, _) in zip(s["kinds"], s["rules"], strict=True):
                used[kind] += 1
                if kind == "binding" and rule == 575:
                    used["binding575"] += 1
        failures.append(
            {
                "program": f.parent.name,
                "paid": native["paid"],
                "native_untriggered": count["untriggered_rule"],
                "native_binding": count["binding"],
                "native_binding575": count["binding575"],
                "pages": len(packets),
                "unique_page_template_examples": used["template"],
                "unique_page_binding_examples": used["binding"],
                "unique_page_binding575_examples": used["binding575"],
            }
        )
    write_csv(dest / "failure-data.csv", failures)


def frozen_results(root, dest):
    states = Counter()
    first_gap = []
    summed = defaultdict(Counter)
    for path in sorted(root.glob("frozen/*/*/curves.csv")):
        seen = set()
        pairs = defaultdict(set)
        for row in rows(path):
            source, case, arm = [row[k] for k in ("source", "case", "arm")]
            seed, draw, budget = [
                int(row[k]) for k in ("fit_seed", "draw_seed", "budget")
            ]
            run = int(row["run"])
            seen.add(run)
            key = (arm, seed, draw, budget)
            if (
                key in pairs[run]
                or not 0
                <= int(row["matched_productive"])
                <= int(row["matched"])
                <= int(row["issued"])
                <= int(row["goal"])
                <= budget
            ):
                raise ValueError((path, run, key))
            pairs[run].add(key)
            if (
                source == "rollout"
                and int(row["run"]) == 3
                and not case.startswith("grammar")
                and budget == 256
            ):
                first_gap.append(
                    {
                        k: row[k]
                        for k in (
                            "case",
                            "arm",
                            "fit_seed",
                            "draw_seed",
                            "issued575",
                            "binding575",
                            "distinct575",
                        )
                    }
                )
            group = summed[source, case, arm, seed, draw, budget]
            for k in (
                "goal",
                "issued",
                "productive",
                "physical_repeat",
                "matched",
                "matched_productive",
                "unknown",
                "hit_draws",
                "untriggered",
                "issued575",
                "binding575",
                "distinct575",
            ):
                group[k] += int(row[k])
            if budget == 256:
                group["slot_attempts"] += int(row["attempts_full"])
        expected = {
            (arm, seed, draw, budget)
            for arm, seed in [
                ("factored", 0),
                *((arm, seed) for arm in ARMS for seed in SEEDS),
            ]
            for draw in range(5)
            for budget in BUDGETS
        }
        if not all(v == expected for v in pairs.values()):
            raise ValueError(f"incomplete paired budgets in {path}")
        states[source] += len(seen)
    if states != {"teacher": 109, "rollout": 76}:
        raise ValueError(f"incomplete frozen states: {states}")
    write_csv(dest / "run3.csv", first_gap)
    keys = ["source", "case", "arm", "fit_seed", "draw_seed", "budget"]
    write_csv(
        dest / "frozen-seeds.csv",
        [dict(zip(keys, k), **v) for k, v in sorted(summed.items())],
    )
    totals = defaultdict(Counter)
    for (src, case, arm, seed, draw, b), v in summed.items():
        totals[src, arm, seed, draw, b].update(v)
    results = defaultdict(list)
    for (src, arm, seed, draw, b), v in totals.items():
        base = totals[src, "factored", 0, draw, b]
        results[src, arm, b].append(
            dict(
                v,
                win=int(v["matched_productive"] > base["matched_productive"]),
                tie=int(v["matched_productive"] == base["matched_productive"]),
            )
        )
    write_csv(
        dest / "frozen.csv",
        [
            dict(
                source=src,
                arm=arm,
                budget=b,
                pairs=len(records),
                **{k: mean(r[k] for r in records) for k in records[0]},
            )
            for (src, arm, b), records in sorted(results.items())
        ],
    )


def native_results(root, dest):
    native = []
    for p in sorted(root.glob("native/*/*/native-address/*/*/run.json")):
        s = read(p)
        if s["termination"] != "schedule_end":
            raise ValueError((p, s["termination"]))
        fit, draw = p.relative_to(root).parts[1:3]
        native.append(
            {
                "case": s["case"],
                "arm": s["method"],
                "fit_seed": fit,
                "draw_seed": draw,
                "block": s["block"],
                "facts": s["covered"],
                "reference": s["reference"],
                "graph": s["state_sha"],
                "paid": s["paid"],
                "ops": s["signed_ops"],
                "EPT": s["ept"],
                "EPS": s["cold_eps"],
                "seconds": s["cold_wall"],
                "accepted": s["verdicts"].get("accepted", 0),
                "untriggered": s["verdicts"].get("untriggered_rule", 0),
                "binding": s["verdicts"].get("binding", 0),
                "slots": s["device"].get("neural_slot_attempts", 0),
                "unfilled": s["device"].get("complete_shortfall", 0),
            }
        )
    if len(native) != 64:
        raise ValueError(f"incomplete native records: {len(native)}/64")
    write_csv(dest / "native-runs.csv", native)
    by = defaultdict(list)
    for r in native:
        by[r["case"], r["arm"]].append(r)
    result = []
    for (case, arm), records in sorted(by.items()):
        origins = [r for r in records if r["block"] == 0]
        timing = [r for r in records if r["fit_seed"] == "9633"]
        assert (
            len(origins) == 3
            and len(timing) == 2
            and len({r["graph"] for r in timing}) == 1
        )
        result.append(
            dict(
                case=case,
                arm=arm,
                reference=records[0]["reference"],
                **{
                    k: mean(r[k] for r in origins)
                    for k in (
                        "facts",
                        "paid",
                        "ops",
                        "EPT",
                        "untriggered",
                        "binding",
                        "slots",
                        "unfilled",
                    )
                },
                EPS=median(r["EPS"] for r in timing),
                min_seconds=min(r["seconds"] for r in timing),
                max_seconds=max(r["seconds"] for r in timing),
            )
        )
    write_csv(dest / "native.csv", result)
    write_csv(
        dest / "weights.csv",
        [
            {
                "fit_seed": seed,
                "arm": arm,
                "sha256": hashlib.sha256(
                    (root / "weights" / str(seed) / f"{arm}.pt").read_bytes()
                ).hexdigest(),
            }
            for seed in SEEDS
            for arm in ARMS
        ],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    a.dest.mkdir(parents=True, exist_ok=True)
    training_results(a.root, a.dest)
    frozen_results(a.root, a.dest)
    native_results(a.root, a.dest)
