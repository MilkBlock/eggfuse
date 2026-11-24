"""Archive per-Run costs, recovery and semantic endpoint coverage for frozen policies."""

import argparse
import csv
import json
import subprocess
from pathlib import Path
from statistics import mean

from recursive_rollout import EVAL
from recursive_train import binary, folder, read


def report(root, out):
    out.mkdir(exist_ok=True, parents=True)
    exp = root / "recursive-agent"
    summary = []
    curves = []
    for case in EVAL:
        c = read(exp / (case + "-coverage.json"))
        for arm in ("legacy", "two", "free", "pending"):
            work = exp / (case + "-" + arm)
            m = read(work / "metrics.json")
            v = c[arm]
            trace = m["trace"]
            assert len(trace) == len(v["curve"])
            certified = json.loads(
                subprocess.check_output(
                    [
                        binary(root),
                        "replay",
                        folder(root, case) / "program.json",
                        work / "issued.json",
                        "time",
                        str(m["common"]),
                        "--ept",
                    ]
                )
            )
            prefix_ops = sum(certified["ept"]["signed_external"]) + sum(
                certified["ept"]["signed_internal"]
            )
            meter = m["counts"]
            rejects = sum(meter["rejected"].values())
            assert m["paid"] == meter["accepted"] + meter[
                "duplicates"
            ] + rejects + m.get("unobserved_verdicts", 0)
            assert m["signed_ops"] >= prefix_ops
            assert v["reference_groundable"] == v["all"][1]
            fronts = [t[5] for t in trace if t[5] is not None]
            summary.append(
                dict(
                    case=case,
                    arm=arm,
                    termination=m["termination"],
                    failure=m["failure"],
                    failure_run=m.get("failed_run"),
                    reference_commits=read(folder(root, case) / "capture.json")[
                        "matches"
                    ],
                    reference_sha=m["reference_sha"],
                    state_sha=m["state_sha"],
                    exact_endpoint=m["final_equal"],
                    runs=m["runs"],
                    first_divergent=m["common"] + 1 if not m["final_equal"] else None,
                    all=v["all"],
                    derived=v["derived"],
                    first_missed=v["first_missed"],
                    later_recovered=v["later_recovered"],
                    paid=m["paid"],
                    effective_ops=m["ops"],
                    signed_ops=m["signed_ops"],
                    certified_prefix_ops=prefix_ops,
                    ept=m["ept"],
                    eps=m["eps"],
                    wall=m["wall"],
                    visits=m["visits"],
                    visits_per_op=m["visits"] / max(1, m["signed_ops"]),
                    duplicates=meter["duplicates"],
                    reject=meter["rejected"],
                    duplicate_rate=meter["duplicates"] / max(1, m["paid"]),
                    reject_rate=rejects / max(1, m["paid"]),
                    accepted=meter["accepted"],
                    unobserved=m.get("unobserved_verdicts", 0),
                    pool=[max(t[4] for t in trace), trace[-1][4]],
                    frontier_mean=mean(fronts) if fronts else None,
                    frontier_max=max(fronts, default=None),
                    work=m["work"],
                    read_work=m.get("read_work", {}),
                )
            )
            for i, (z, row) in enumerate(zip(trace, v["curve"], strict=True)):
                curves.append(
                    dict(
                        case=case,
                        arm=arm,
                        run=z[0],
                        elapsed=trace[i + 1][6] if i + 1 < len(trace) else m["wall"],
                        derived=row["derived"],
                        denominator=v["derived"][1],
                        all_rows=row["covered"],
                        all_denominator=v["all"][1],
                        paid=z[2],
                        visits=z[3],
                        pool=z[4],
                        frontier=z[5],
                        reference_run=row["due_run"],
                        ever_overdue=row["overdue"],
                        ever_recovered=row["recovered"],
                    )
                )
    frozen = [read(f) for f in sorted(exp.glob("*-frozen.json"))]
    out.joinpath("results.json").write_text(
        json.dumps(dict(exclusive=summary, shadow=frozen), indent=2) + "\n"
    )
    with (out / "runs.csv").open("w", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=list(curves[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(curves)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    report(a.root.resolve(), a.output)
