"""Compare an empty neural source Run to a one-Run exact fork of that same state."""

import argparse
import json
import subprocess
from pathlib import Path

from recursive_rollout import EVAL
from recursive_train import binary, folder, read


def audit(root, case, arm, series):
    d = folder(root, case)
    w = root / series / f"{case}-{arm}-multi"
    m = read(w / "metrics.json")
    ref = read(d / "capture.json")
    sched = read_schedule(root, d, w, m)

    def coord(s):
        return s[0], tuple(s[1]), tuple(s[2])

    gold = {coord(s): s[4] for s in ref["schedule"]}
    empty = [j for j, s in enumerate(sched) if s[4] == 0]
    suspect = next((j for j in empty if gold.get(coord(sched[j]), 0) > 0), None)
    checks = []
    for j in sorted(
        {k for k in (suspect, empty[-1] if empty else None) if k is not None}
    ):
        x = json.loads(
            subprocess.check_output(
                [
                    binary(root),
                    "replay",
                    d / "program.json",
                    w / "issued.json",
                    "time",
                    str(j),
                    "--audit-exact-next",
                ]
            )
        )
        assert x["run"] == j + 1
        checks.append(
            dict(
                run=j + 1,
                teacher=gold.get(coord(sched[j])),
                last_empty=j == empty[-1],
                **x["result"],
            )
        )
    return dict(
        case=case, arm=arm, series=series, observed_empty=len(empty), checks=checks
    )


def read_schedule(root, d, w, m):
    return json.loads(
        subprocess.check_output(
            [
                binary(root),
                "replay",
                d / "program.json",
                w / "issued.json",
                "time",
                str(m["runs"]),
            ]
        )
    )["schedule"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    r = a.root.resolve()
    results = [
        audit(r, c, arm, "cell-stream")
        for c in EVAL
        for arm in ("fixed", "dynamic", "dense", "stream")
    ]
    results += [
        audit(r, c, "stream", "cell-stream-long")
        for c in ("cyk801", "sum-divisors", "jacobi")
    ]
    a.output.write_text(json.dumps(results, indent=2) + "\n")
