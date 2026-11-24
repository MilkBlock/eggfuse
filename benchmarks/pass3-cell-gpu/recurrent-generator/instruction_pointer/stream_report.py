"""Per-Run native coverage and metered resources on each arm's own trajectory."""

import csv
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_coverage import Target, snapshot
from recursive_rollout import EVAL
from recursive_train import binary, folder, read


def report(
    root,
    dest,
    series="cell-stream",
    cases=EVAL,
    arms=("fixed", "dynamic", "dense", "stream"),
):
    result = []
    curves = []
    for case in cases:
        d = folder(root, case)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            target, ref = snapshot(root, d, "reference", "-", None, path / "gold.json")
            goal = Target(read(d / "program.json"), target)
            seed = goal.match(
                snapshot(root, d, "reference", "-", 0, path / "initial.json")[0]
            )
            denominator = len(goal.gold) - len(seed)
            assert len(goal.match(target)) == len(goal.gold)
            for arm in arms:
                w = root / series / f"{case}-{arm}-multi"
                m = read(w / "metrics.json")
                log = path / "rows.jsonl"
                replay = json.loads(
                    subprocess.check_output(
                        [
                            binary(root),
                            "replay",
                            d / "program.json",
                            w / "issued.json",
                            "time",
                            str(m["runs"]),
                            "--row-history",
                            log,
                        ]
                    )
                )
                assert replay["state_sha"] == m["state_sha"]
                state = {}
                have = set()
                coord = None
                for s in map(json.loads, log.open()):
                    for k in s["removed"]:
                        del state[k]
                    for k in s["added"]:
                        state[k] = json.loads(k)
                    if s["added"] or s["removed"] or not s["run"]:
                        have = goal.match({"rows": state.values()}) - seed
                    t = m["trace"][s["run"] - 1] if s["run"] else {}
                    coord = dict(
                        case=case,
                        arm=arm,
                        run=s["run"],
                        elapsed=t.get("elapsed", 0),
                        paid=t.get("paid", 0),
                        visits=t.get("visits", 0) + t.get("interface_reads", 0),
                        covered=len(have),
                        reference=denominator,
                    )
                    curves.append(coord)
                visits = m["work"].get("visits", 0) + m["work"].get(
                    "interface_reads", 0
                )
                curves.append(
                    {**coord, "elapsed": m["wall"], "visits": visits, "paid": m["paid"]}
                )
                rejects = {
                    v: n
                    for v, n in m["verdicts"].items()
                    if v not in ("accepted", "duplicate")
                }
                assert m["paid"] == sum(m["verdicts"].values())
                result.append(
                    {
                        **{k: v for k, v in m.items() if k != "trace"},
                        "derived": [len(have), denominator],
                        "reference_runs": ref["runs"],
                        "reference_commits": ref["matches"],
                        "visits": visits,
                        "duplicate_rate": m["verdicts"].get("duplicate", 0)
                        / max(1, m["paid"]),
                        "reject_rate": sum(rejects.values()) / max(1, m["paid"]),
                    }
                )
    (dest / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    with (dest / "runs.csv").open("w") as stream:
        w = csv.DictWriter(stream, fieldnames=list(curves[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(curves)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--series", default="cell-stream")
    parser.add_argument("--cases", nargs="+", default=EVAL)
    parser.add_argument(
        "--arms", nargs="+", default=["fixed", "dynamic", "dense", "stream"]
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report(args.root.resolve(), args.out, args.series, args.cases, args.arms)
