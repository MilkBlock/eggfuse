"""Collect the paired observations without treating timing repetitions as independent template tests."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def timing(values):
    median = statistics.median(values)
    return dict(median=median, mad=statistics.median(abs(x - median) for x in values), values=values)


def collect(store):
    cases = read(store / "prediction.json")["tests"]
    output = {}
    for case in cases:
        output[case] = {}
        for arm in ("A", "B", "C", "serial", "Cdecode"):
            runs = [read(store / f"live-{case}-{arm}-{i}.json") for i in range(4)]
            if len({(r["covered_sha"], r["state_sha"], r["paid"], r["signed_ops"]) for r in runs}) != 1:
                raise ValueError(("non-repeatable semantic endpoint", case, arm))
            output[case][arm] = dict(eps=timing([r["end_to_end_eps"] for r in runs]), runs=runs)
        a, b = (output[case][arm]["runs"][0] for arm in ("A", "B"))
        assert (a["state_sha"], a["paid"]) == (b["state_sha"], b["paid"])
        output[case]["search_audit"] = {
            arm: read(store / f"audit-{case}-{arm}-0.json")["work"].get(
                "revisited_identical_pointer_positions", 0
            )
            for arm in ("A", "C")
        }
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("store", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    a.dest.mkdir(exist_ok=True, parents=True)
    (a.dest / "independent.json").write_text(json.dumps(collect(a.store), indent=2) + "\n")
    files = sorted([*a.store.glob("*.jsonl"), a.store / "state137.pt", a.store / "higher-flow.pt"])
    (a.dest / "inputs.json").write_text(
        json.dumps({f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}, indent=2) + "\n"
    )
