"""Summarize signed native runs, optimizer exposure and held-out recall separately."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


def read(path):
    return json.loads(path.read_text())


def lines(path):
    with path.open() as stream:
        return list(map(json.loads, stream))


def table(folder, name, rows):
    if rows:
        with (folder / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def write_native(root, out):
    grouped = defaultdict(list)
    facts = {}
    issued = []
    for path in sorted(root.glob("native/*/*/native-address/*/*/run.json")):
        seed, draw = map(int, path.relative_to(root).parts[1:3])
        v = read(path)
        arm, case = v["method"], v["case"]
        assert v["termination"] == "schedule_end" and len(v["facts"]) == v["covered"]
        assert sum(v["verdicts"].values()) == v["paid"]
        facts[case, v["state_sha"]] = v["facts"]
        for kind in (
            "accepted",
            "duplicate",
            "untriggered_rule",
            "binding",
            "guard",
            "watermark",
        ):
            v.setdefault(kind, v["verdicts"].get(kind, 0))
        row = {
            "case": case,
            "arm": arm,
            "seed": seed,
            "draw": draw,
            "block": v["block"],
            "graph": v["state_sha"],
            "reference": v["reference"],
            "covered": v["covered"],
            "effective": v["signed_ops"],
            "paid": v["paid"],
            "EPT": v["ept"],
            "EPS": v["cold_eps"],
            "seconds": v["cold_wall"],
            "physical_repeat": v["work"].get("same_run_repeat_signed", 0),
        }
        row.update(
            {
                k: v[k]
                for k in (
                    "accepted",
                    "duplicate",
                    "untriggered_rule",
                    "binding",
                    "guard",
                    "watermark",
                )
            }
        )
        grouped[case, arm].append(row)
        issued.append(row)
    if len(issued) != 17 * 4 * 3:
        raise ValueError("missing policy, workload or native timing block")
    for row in issued:
        case, seed, block = row["case"], row["seed"], row["block"]
        control = next(
            x
            for x in grouped[case, "factored"]
            if x["seed"] == seed and x["block"] == block
        )
        a = set(facts[case, row["graph"]])
        b = set(facts[case, control["graph"]])
        row.update(only_model=len(a - b), only_random=len(b - a), shared=len(a & b))
    table(out, "native-runs.csv", issued)
    summary = []
    for (case, arm), rows in grouped.items():
        quality = [v for v in rows if v["block"] == 0]
        timing = [v for v in rows if v["seed"] == 9633]
        assert (
            len(timing) == 2
            and len({v["graph"] for v in timing}) == 1
            and len(quality) == 2
        )
        summary.append(
            {
                "case": case,
                "arm": arm,
                "Coverage": mean(v["covered"] / v["reference"] for v in quality),
                "EPT": mean(v["EPT"] for v in quality),
                "EPS": median(v["EPS"] for v in timing),
                "seconds_min": min(v["seconds"] for v in timing),
                "seconds_max": max(v["seconds"] for v in timing),
                "paid": mean(v["paid"] for v in quality),
                "only_model": mean(v["only_model"] for v in quality),
                "only_random": mean(v["only_random"] for v in quality),
            }
        )
    table(out, "native.csv", summary)
    with (out / "native-facts.jsonl").open("w") as f:
        for (case, graph), ids in sorted(facts.items()):
            f.write(
                json.dumps(
                    {"case": case, "graph": graph, "facts": ids}, separators=(",", ":")
                )
                + "\n"
            )


def other_tests(root, out):
    held = lines(root / "held-dags.jsonl")
    if len(held) != 10 * 8 * 2:
        raise ValueError("incomplete held-DAG trials")
    groups = defaultdict(list)
    for v in held:
        groups[v["arm"]].append(v)
    table(
        out,
        "held-dags.csv",
        [
            {
                "arm": k,
                "trials": len(v),
                "coverage": mean(x["covered"] / x["reference"] for x in v),
                "EPT": mean(x["EPT"] for x in v),
                "EPS": mean(x["EPS"] for x in v),
                "paid": mean(x["paid"] for x in v),
            }
            for k, v in groups.items()
        ],
    )
    groups = defaultdict(lambda: defaultdict(int))
    files = sorted(root.glob("frozen/rollout/*/curves.csv"))
    if len(files) != 4:
        raise ValueError("missing frozen workload results")
    for path in files:
        with path.open() as stream:
            for v in csv.DictReader(stream):
                k = (
                    v["case"],
                    v["arm"],
                    int(v["budget"]),
                    int(v["fit_seed"]),
                    int(v["draw_seed"]),
                )
                for field in (
                    "matched",
                    "matched_productive",
                    "issued",
                    "hit_draws",
                    "physical_repeat",
                    "untriggered",
                    "unknown",
                ):
                    groups[k][field] += int(v[field])
    table(
        out,
        "frozen-pairs.csv",
        [
            dict(case=c, arm=a, budget=b, fit_seed=s, draw=d, **counts)
            for (c, a, b, s, d), counts in sorted(groups.items())
        ],
    )
    combined = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for (_, arm, budget, seed, draw), counts in groups.items():
        metrics = combined[arm, budget][seed, draw]
        for k, v in counts.items():
            metrics[k] += v
    overall = []
    for (arm, budget), pairs in sorted(combined.items()):
        scores = list(pairs.values())
        overall.append(
            {
                "arm": arm,
                "budget": budget,
                "matched": mean(p["matched"] for p in scores),
                "discoveries": mean(p["matched_productive"] for p in scores),
                "repeat_fraction": mean(
                    p["physical_repeat"] / p["issued"] for p in scores
                ),
                "untriggered_fraction": mean(
                    p["untriggered"] / p["issued"] for p in scores
                ),
            }
        )
    table(out, "frozen.csv", overall)
    rr = lines(Path(__file__).parent / "run-recall/response-edit/runs.jsonl")
    historic = []
    for v in rr:
        if v["arm"] == "A":
            historic.append(
                {
                    key: v[key]
                    for key in (
                        "case",
                        "block",
                        "covered",
                        "reference",
                        "paid",
                        "signed_ops",
                        "ept",
                        "cold_eps",
                        "cold_wall",
                        "state_sha",
                    )
                }
            )
    table(out, "historical-stream.csv", historic)


def training(root, out):
    result = []
    batches = defaultdict(list)
    for path in sorted((root / "weights").glob("*/*.json")):
        v = read(path)
        h = v["history"]
        row = {
            "model": path.stem,
            "seed": v["seed"],
            "checkpoint_sha": hashlib.sha256(
                path.with_suffix(".pt").read_bytes()
            ).hexdigest(),
            "updates": len(h),
            "seen_programs": len({x[0] for x in h}),
            "seen_source_state_tuples": len({tuple(x[:3]) for x in h}),
            "sampled_slots": sum(x[5] for x in h),
            "used_tokens": sum(x[6] for x in h),
            "teacher_updates": sum(x[1] == "teacher" for x in h),
            "pure_updates": sum(x[1] == 2 for x in h),
            "group_seconds": v["group_seconds"],
            "group_checkpoints": v["group_arms"],
        }
        result.append(row)
        batches[v["group_seconds"]].append(row)
    table(out, "training.csv", result)
    throughput = []
    for elapsed, rows in batches.items():
        assert len(rows) == rows[0]["group_checkpoints"]
        n = sum(x["used_tokens"] for x in rows)
        throughput.append(
            {
                "models": " ".join(sorted({x["model"] for x in rows})),
                "seconds": elapsed,
                "checkpoints": len(rows),
                "optimizer_tokens": n,
                "tokens_per_second": n / elapsed,
            }
        )
    table(out, "training-throughput.csv", throughput)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    training(a.root, a.output)
    write_native(a.root, a.output)
    other_tests(a.root, a.output)
