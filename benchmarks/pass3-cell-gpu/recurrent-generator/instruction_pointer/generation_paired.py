"""Run counterbalanced independent trials after the exploratory sweeps."""

import argparse
import json
import subprocess
from time import perf_counter
from recursive_train import binary, folder
from pathlib import Path
import torch
from generation_frontier import CASES, experiment
from protocol_experiment import dump


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    for case in CASES:
        trials = []
        treatments = (
            ("A", 0),
            ("B", 0),
            ("residual", 0),
            ("fixed", 0),
            ("trained", 0),
            ("unranked", 0),
            ("A", -3),
            ("trained", -3),
            ("A", -1),
        )
        control = []
        for rep in range(1, 5):
            order = (
                treatments
                if rep <= 2
                else treatments[len(treatments) // 2 :]
                + treatments[: len(treatments) // 2]
            )
            if rep % 2 == 0:
                order = order[::-1]
            for arm, cut in order:
                m = experiment(args.root, args.out, case, arm, cut, rep)
                trials.append(
                    {
                        k: m[k]
                        for k in (
                            "arm",
                            "threshold",
                            "repeat",
                            "state_sha",
                            "coverage",
                            "reference",
                            "paid_total",
                            "signed_ops",
                            "ept",
                            "eps",
                            "wall",
                            "native_verify_seconds",
                            "verdicts",
                        )
                    }
                    | dict(visits=m["work"].get("visits", 0))
                )
                dump(args.out / f"paired-{case}.json", trials)
            d = folder(args.root, case)
            row = {}
            for mode in ("reference", "replay") if rep % 2 else ("replay", "reference"):
                t = perf_counter()
                report = json.loads(
                    subprocess.check_output(
                        [
                            binary(args.root),
                            mode,
                            d / "program.json",
                            "-" if mode == "reference" else d / "tape.json",
                            "time",
                        ]
                    )
                )
                row[mode] = perf_counter() - t
                if "sha" in row and row["sha"] != report["state_sha"]:
                    raise ValueError("teacher replay diverged")
                row["sha"] = report["state_sha"]
            control.append(row)
            dump(args.out / f"oracle-{case}.json", control)


if __name__ == "__main__":
    main()
