"""Check emitted parent tickets, exact source audits, guard receipts, counts and sample medians."""

import argparse
import json
from pathlib import Path
from statistics import median


def validate(table, controls):
    required = {
        "sum-bits-1703",
        "dot-product-1703",
        "jacobi-1d-1703",
        "conjugate-gradient-1703",
    }
    assert set(table) == required
    for name, arms in table.items():
        original = arms["off"]
        for mode, entry in arms.items():
            if mode not in ("stale", "foreign"):
                assert (
                    len(entry["ms"]) >= 5 and median(entry["ms"]) == entry["median_ms"]
                )
            if mode == "vanilla":
                continue
            assert entry["aligned"] and all(entry["checks"].values())
            assert entry["neural_rhs"] == entry["rhs"] == arms["vanilla"]["rhs"]
            assert entry["direct_cells"] >= 0.98 * entry["fresh"]
            for key in (
                "cells",
                "multi_sources",
                "root_parents",
                "root_ids",
                "nested_ids",
                "state_sha",
            ):
                assert entry[key] == original[key]
            assert not entry["counts"]["exhausted"]
            if mode in ("stale", "foreign"):
                assert (
                    entry["raw"] == original["raw"]
                    and entry["multi"] == original["multi"]
                )
                assert entry["counts"] == original["counts"]
                assert all(v["work"]["probes"] == 0 for v in entry["rules"].values())
            if mode in ("local", "constants"):
                r = entry["rules"]["10"]["work"]
                assert (
                    sum(v["work"]["zero_probes"] for v in entry["rules"].values()) > 0
                )
                if name.startswith(("jacobi", "conjugate")):
                    assert r["zero_probes"] > 0 and r["output_tests"] > 0
                assert all(
                    v["work"]["invalid_receipts"] == 0 for v in entry["rules"].values()
                )
                assert entry["counts"]["raw_tuples"] <= original["counts"]["raw_tuples"]
        if controls:
            assert {"stale", "foreign"} <= arms.keys()
        assert (
            arms["local"]["counts"]["raw_tuples"]
            <= arms["constants"]["counts"]["raw_tuples"]
        )
        print(
            name,
            [
                (
                    k,
                    round(arms[k]["median_ms"], 2),
                    arms[k]["counts"]["raw_tuples"],
                    arms[k]["per_rule"].get("10", {}).get("raw"),
                )
                for k in ("off", "constants", "local")
            ],
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("result", type=Path)
    p.add_argument("--controls", action="store_true")
    a = p.parse_args()
    validate(json.loads(a.result.read_bytes()), a.controls)
