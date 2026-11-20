"""Check whole-program parity, model provenance, page faults, immutable column reuse, and source budgets."""

import argparse
import json
from pathlib import Path
from statistics import median


def verify(path):
    table = json.loads(path.read_bytes())
    assert set(table) == {"sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient"}
    assert (
        sum(
            r["arms"]["changed"]["typed"]["reused_after_change"] for r in table.values()
        )
        > 0
    )
    for case, r in table.items():
        arm = r["arms"]
        base = arm["legacy"]
        assert len(r["faults"]) == 3 and all(
            "no verified root recipe" in failure[1] for failure in r["faults"].values()
        )
        for name, v in arm.items():
            assert (
                len(v["ms"]) >= 5
                and median(v["ms"]) == v["median_ms"]
                and median(v["wall_ms"]) == v["wall_median_ms"]
            )
            if name == "vanilla":
                continue
            assert (
                all(v["checks"].values())
                and v["rhs"] == v["neural_rhs"] == arm["vanilla"]["rhs"]
            )
            assert 100 * v["direct_cells"] >= 98 * v["fresh"]
            for key in (
                "state_sha",
                "cells",
                "single_winners",
                "multi_winners",
                "root_ids",
                "root_parents",
                "nested_ids",
            ):
                assert v[key] == base[key]
        for group in [
            ("constant", "archive", "pages"),
            ("signed", "integrated", "typed", "typed256", "changed"),
        ]:
            reference = arm[group[0]]
            for name in group:
                for k in (
                    "raw",
                    "commits",
                    "multi",
                    "single_digest",
                    "single_headers",
                    "single_issued",
                    "raw_packets",
                ):
                    assert arm[name][k] == reference[k]
        for name in ("pages", "integrated", "typed", "typed256", "changed"):
            assert (
                arm[name]["raw_packets"] == arm[name]["packed"] > arm[name]["pages"] > 0
            )
        for name, bound in [
            ("typed", 65536),
            ("typed256", 262144),
            ("changed", 262144),
        ]:
            idx = arm[name]["typed"]
            assert (
                0 < idx["peak_bytes"] <= bound
                and idx["verified"] > 0
                and idx["full_hits"] > 0
            )
        assert arm["changed"]["typed"]["tracked_batches"] > 0
        print(
            case,
            round(arm["integrated"]["median_ms"], 2),
            round(arm["changed"]["median_ms"], 2),
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "results",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("results.json"),
    )
    verify(p.parse_args().results)
