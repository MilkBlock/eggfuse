"""Validate whole-program endpoints, budgeted signed filtering, and conservative directory updates."""

import json
import sys
from pathlib import Path
from statistics import median


def check(path, old):
    results = json.loads(path.read_bytes())
    original = json.loads(old.read_bytes())
    assert set(results) == set(original)
    for case, r in results.items():
        reference = original[case]["arms"]["integrated"]
        m = r["arms"]
        assert len(r["faults"]) == 3
        for name, v in m.items():
            assert len(v["ms"]) == 5 and median(v["ms"]) == v["median_ms"]
            if name == "vanilla":
                continue
            assert (
                all(v["checks"].values())
                and v["rhs"] == v["neural_rhs"] == m["vanilla"]["rhs"]
            )
            assert 100 * v["direct_cells"] >= 98 * v["fresh"]
            for k in (
                "single_winners",
                "multi_winners",
                "root_ids",
                "root_parents",
                "nested_ids",
                "state_sha",
                "cells",
                "fresh",
                "direct_cells",
                "raw_packets",
            ):
                assert v[k] == reference[k], (case, name, k)
            if name in ("both", "sparse", "all"):
                assert v["typed"]["skipped_cold_rows"] > 0
            if name in ("epochs", "both", "all"):
                assert v["typed"]["epoch_updates"] > 0 and v["typed"]["epoch_audit"] > 0
            if name in ("integrated", "sparse"):
                assert (
                    v["single_digest"] == reference["single_digest"]
                    and v["single_issued"] == reference["single_issued"]
                )
        print(case, [(k, round(v["median_ms"], 2)) for k, v in m.items()])


if __name__ == "__main__":
    d = Path(__file__).parent
    check(
        Path(sys.argv[1]) if len(sys.argv) > 1 else d / "directory-results.json",
        d / "results.json",
    )
