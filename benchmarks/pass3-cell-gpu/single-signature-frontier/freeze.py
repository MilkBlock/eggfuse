"""Freeze an admission policy using relative complete-pass costs on four training programs."""

import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

from measure import TRAIN, settings


def choose(study, out):
    matrix = json.loads(study.read_bytes())
    assert set(matrix) == set(TRAIN)
    specs = settings(SimpleNamespace(phase="calibrate"))
    cost = {}
    for name in specs:
        rel = [
            arms[name]["median_ms"] / arms["off"]["median_ms"]
            for arms in matrix.values()
        ]
        cost[name] = math.exp(sum(map(math.log, rel)) / len(rel))
    selected = min(
        (m for m, v in specs.items() if v and v["bytes"] > 0),
        key=lambda m: (cost[m], specs[m]["bytes"]),
    )
    out.mkdir(parents=True, exist_ok=False)
    (out / "admission.json").write_text(json.dumps(specs[selected], indent=1) + "\n")
    (out / "selection.json").write_text(
        json.dumps(
            {"cases": sorted(matrix), "scores": cost, "selected": selected}, indent=1
        )
        + "\n"
    )
    print(selected, specs[selected], cost)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("study", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    choose(a.study, a.out)
