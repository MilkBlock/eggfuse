"""Held-out decision-cost diagnostics collected only after freezing the learned scheduler."""

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from runner import materialize, rpc


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for case in ("jacobi-1d", "conjugate-gradient"):
        for seed in (1703, 1709):
            prog, plan, _, req = materialize(
                a.exp, a.out, case, seed, "certified", a.large
            )
            with subprocess.Popen(
                [a.binary, prog, plan],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as proc:
                all_sizes = []
                all_costs = []
                for i in range(2):
                    settings = {
                        "action": 4,
                        "max_rows": 8,
                        "workers": 8,
                        "capture": True,
                        "seed": seed * 123457 + i * 2305843009213693951,
                    }
                    data = rpc(proc, dict(req, audit=False, rows=settings))
                    assert "source_error" not in data
                    for x, y in data["single"]["adaptive_rows"]["examples"]:
                        all_sizes.append(round(2 ** (12 * x[0]) - 1))
                        all_costs.append(y)
                sizes = np.array(all_sizes)
                costs = np.array(all_costs)
                bins = {}
                for lo, hi in (
                    (1, 1),
                    (2, 15),
                    (16, 63),
                    (64, 255),
                    (256, 1023),
                    (1024, 2**31),
                ):
                    group = costs[(sizes >= lo) & (sizes <= hi)]
                    if len(group):
                        bins[str(lo)] = {
                            "n": len(group),
                            "mean_us": (group.mean(0) / 1e3).tolist(),
                            "fastest": np.bincount(
                                group.argmin(1), minlength=8
                            ).tolist(),
                        }
                summary[f"{case}/{seed}"] = {
                    "size_quantiles": np.percentile(
                        sizes, [0, 50, 90, 99, 100]
                    ).tolist(),
                    "bins": bins,
                }
                (a.out / "results.json").write_text(
                    json.dumps(summary, indent=1) + "\n"
                )
                proc.stdin.close()
                proc.wait()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("binary", "exp", "large", "out"):
        p.add_argument(k, type=Path)
    run(p.parse_args())
