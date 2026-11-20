"""Archive timing samples, structural and physical audit hashes, measured hot rules and the static catalog."""

import argparse
import json
from pathlib import Path

from verify import validate


def pack(path, controls):
    d = json.loads(path.read_bytes())
    validate(d, controls)
    report = {}
    for case, arms in d.items():
        group = {}
        for arm, v in arms.items():
            if arm == "vanilla":
                group[arm] = v
                continue
            keep = (
                "ms",
                "median_ms",
                "checks",
                "rhs",
                "neural_rhs",
                "cells",
                "fresh",
                "direct_cells",
                "state_sha",
                "multi_sources",
                "root_parents",
                "root_ids",
                "nested_ids",
                "raw",
                "multi",
                "counts",
            )
            data = {k: v[k] for k in keep if k in v}
            rules = v["rules"]
            totals = {}
            for r in rules.values():
                for k, val in r["work"].items():
                    if isinstance(val, int):
                        totals[k] = (
                            max(totals.get(k, 0), val)
                            if k.startswith("peak_")
                            else totals.get(k, 0) + val
                        )
            data.update(
                guard_work=totals,
                rule_10=v["per_rule"].get("10"),
                rule_10_guards=rules.get("10", {}).get("work"),
            )
            group[arm] = data
        report[case] = group
    return report, d["jacobi-1d-1703"]["local"]["catalog"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pair", type=Path)
    p.add_argument("corr", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    pair, catalog = pack(a.pair, True)
    corr, other = pack(a.corr, False)
    assert catalog == other
    (a.out / "results.json").write_text(
        json.dumps({"pair": pair, "correlated": corr}, indent=1) + "\n"
    )
    (a.out / "catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")
