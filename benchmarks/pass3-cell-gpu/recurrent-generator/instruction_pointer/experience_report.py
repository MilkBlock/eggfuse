"""Publish paired results; one unit is one distinct credited native request signature."""

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


def write(path, rows):
    with path.open("w") as stream:
        w = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def report(root, dest):
    dest.mkdir(parents=True, exist_ok=True)
    inventory = []
    states = []
    for p in sorted(root.glob("experience/*/*/labels.json")):
        labels = json.loads(p.read_text())
        extra = [r for r in labels if r["omitted"]]
        for r in labels:
            audit = r["audit"]
            states.append(
                {
                    "case": p.parent.parent.name,
                    "source": p.parent.name,
                    "run": r["run"],
                    "strata": "+".join(r["strata"]),
                    "observed": len(r["executed"]),
                    "omitted": len(r["omitted"]),
                    "omitted_ops": sum(g for _, g in r["omitted"]),
                    "native_certificates": r["native_certificates"],
                    "fork_extra": audit.get("attempted", 0),
                    "unchanged_credit": audit.get("unchanged_original_credits", ""),
                    "audit_seconds": r["seconds"],
                }
            )
        statuses = {}
        if p.parent.name == "self":
            responses = json.loads((p.parent / "responses.json").read_text())
            statuses = Counter(x["status"] for x in responses)
        inventory.append(
            {
                "case": p.parent.parent.name,
                "source": p.parent.name,
                "states": len(labels),
                "observed_positive": sum(len(s["executed"]) for s in labels),
                "omissions": sum(len(s["omitted"]) for s in labels),
                "states_with_omissions": len(extra),
                "omission_ops": sum(n for r in extra for _, n in r["omitted"]),
                "unchanged_credits_violated": sum(
                    r["audit"].get("unchanged_original_credits") is False
                    for r in labels
                ),
                "native_responses": sum(statuses.values()),
                "receipt_types": json.dumps(statuses, sort_keys=True),
            }
        )
    write(dest / "inventory.csv", inventory)
    write(dest / "training-states.csv", states)
    hashes = []
    for p in sorted(root.glob("weights/*/*.pt")):
        steps = json.loads(p.with_suffix(".json").read_text())
        hashes.append(
            {
                "seed": p.parent.name,
                "arm": p.stem,
                "updates": len(steps),
                "labeled_updates": sum(r[-1] > 0 for r in steps),
                "steps_sampled_hit": sum(r[4] > 0 for r in steps),
                "complete_draws": sum(r[6] for r in steps),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    write(dest / "weights.csv", hashes)
    totals = defaultdict(Counter)
    by_state = defaultdict(set)
    for p in sorted(root.glob("frozen/*/*/curves.csv")):
        for r in csv.DictReader(p.open()):
            src, case, arm = r["source"], r["case"], r["arm"]
            by_state[src, case].add(int(r["run"]))
            key = (
                src,
                case,
                int(r["budget"]),
                arm,
                int(r["fit_seed"]),
                int(r["draw_seed"]),
            )
            for k in (
                "matched",
                "matched_productive",
                "physical_repeat",
                "issued",
                "unknown",
                "distinct575",
                "untriggered",
            ):
                totals[key][k] += int(r[k])
    assert Counter(
        {
            src: sum(len(v) for (s, c), v in by_state.items() if s == src)
            for src in ("rollout", "teacher")
        }
    ) == {"rollout": 76, "teacher": 109}
    for (src, case, b, arm, seed, draw), count in list(totals.items()):
        totals[src, "ALL", b, arm, seed, draw].update(count)
    summary = defaultdict(list)
    for (src, case, b, arm, seed, draw), count in sorted(totals.items()):
        baseline = totals[src, case, b, "factored", 0, draw]
        assert baseline["matched"] == count["matched"]
        diff = count["matched_productive"] - baseline["matched_productive"]
        summary[src, case, b, arm].append(
            {
                "hits": count["matched_productive"],
                "paired_diff": diff,
                "win": int(diff > 0),
                "matched": count["matched"],
                "repeat": count["physical_repeat"],
                "unknown": count["unknown"],
            }
        )
    write(
        dest / "frozen.csv",
        [
            dict(
                source=src,
                case=case,
                budget=b,
                arm=arm,
                pairs=len(rows),
                **{k: mean(r[k] for r in rows) for k in rows[0]},
            )
            for (src, case, b, arm), rows in sorted(summary.items())
        ],
    )
    write(
        dest / "frozen-pairs.csv",
        [
            dict(source=s, case=c, budget=b, arm=a, fit_seed=t, draw=d, **v)
            for (s, c, b, a, t, d), v in sorted(totals.items())
        ],
    )
    runs = []
    facts = {}
    for p in sorted(root.glob("native/*/*/native-address/*/*/run.json")):
        r = json.loads(p.read_text())
        assert (
            r["termination"] == "schedule_end"
            and sum(r["verdicts"].values()) == r["paid"]
        )
        seed, draw = map(int, p.relative_to(root).parts[1:3])
        arm = r["method"]
        facts[seed, r["block"], r["case"], arm] = set(r["facts"])
        runs.append(
            {
                "case": r["case"],
                "arm": arm,
                "seed": seed,
                "draw": draw,
                "block": r["block"],
                "facts": r["covered"],
                "reference": r["reference"],
                "ops": r["signed_ops"],
                "paid": r["paid"],
                "EPT": r["ept"],
                "seconds": r["cold_wall"],
                "EPS": r["cold_eps"],
                "graph": r["state_sha"],
                "attempts": r["device"].get("neural_slot_attempts", 0),
                "shortfall": r["device"].get("complete_shortfall", 0),
                "untriggered": r["verdicts"].get("untriggered_rule", 0),
                "accepted": r["committed_tokens"],
            }
        )
    assert len(runs) == 64, len(runs)
    for r in runs:
        key = r["seed"], r["block"], r["case"]
        mine = facts[key + (r["arm"],)]
        rand = facts[key + ("factored",)]
        r.update(only_model=len(mine - rand), only_random=len(rand - mine))
    write(dest / "native-runs.csv", runs)
    native = []
    for case, arm in sorted({(r["case"], r["arm"]) for r in runs}):
        rows = [r for r in runs if r["case"] == case and r["arm"] == arm]
        first = [r for r in rows if r["block"] == 0]
        paired = [r for r in rows if r["seed"] == 9633]
        assert len(first) == 3 and len(paired) == 2
        native.append(
            {
                "case": case,
                "arm": arm,
                "Coverage": mean(r["facts"] / r["reference"] for r in first),
                "mean_facts": mean(r["facts"] for r in first),
                "EPT": mean(r["EPT"] for r in first),
                "EPS": median(r["EPS"] for r in paired),
                "seconds_min": min(r["seconds"] for r in paired),
                "seconds_max": max(r["seconds"] for r in paired),
                "paired_same_graph": len({r["graph"] for r in paired}) == 1,
            }
        )
    write(dest / "native.csv", native)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    args = p.parse_args()
    report(args.root, args.dest)
