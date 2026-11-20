"""Validate natively timed and audited header banks on frozen eggcc programs."""

import json
from pathlib import Path
from statistics import median

FIELD_HASHES = (
    "sealed",
    "raw_multi",
    "single_winners",
    "multi_winners",
    "cells",
    "root_ids",
    "nested_ids",
    "root_parents",
    "raw",
    "multi",
    "commits",
    "physical",
    "children",
    "issued",
    "direct_cells",
    "state_sha",
)


def verify(path):
    d = json.loads(path.read_bytes())
    for case, arms in d.items():
        vanilla = arms["vanilla"]
        original = arms["compiled"]
        assert len(vanilla["ms"]) >= 4
        for name, v in arms.items():
            if name == "vanilla":
                continue
            assert v["aligned"] and all(v["checks"].values())
            assert (
                v["rhs"] == v["neural_rhs"] == vanilla["rhs"]
                and v["direct_cells"] * 100 >= 98 * v["fresh"]
            )
            assert all(v[k] == original[k] for k in FIELD_HASHES), (case, name)
            if name != "stale":
                assert len(v["ms"]) >= 4 and median(v["ms"]) == v["median_ms"]
                assert len(v["clocks"]) >= 2
                assert all(
                    median(x[k] for x in v["clocks"]) == m
                    for k, m in v["median_clock_ms"].items()
                )
            w = v["header_view"]
            if name in (
                "publication",
                "delta",
                "direct",
                "postings",
                "direct-postings",
                "stale",
            ):
                assert (
                    w["builds"] and w["hits"] and w["checked_rows"] and w["fresh_hits"]
                )
            if name == "stale":
                assert w["stale_rejects"] and not w["delta_updates"]
            if name in ("direct", "direct-postings"):
                assert w["direct_borrows"] and w["direct_materialized"]
            if name in ("postings", "direct-postings") and case in ("3mm", "deriche"):
                r = v["postings"]
                assert (
                    0 < r["peak_bytes"] <= 2 << 20
                    and r["audited"]
                    and r["source_rows"] > r["selected"]
                )
        print(
            case,
            {n: round(q["median_ms"], 2) for n, q in arms.items() if "median_ms" in q},
        )


if __name__ == "__main__":
    import sys

    paths = list(map(Path, sys.argv[1:])) or [
        Path(__file__).with_name(n + ".json")
        for n in ("baseline", "anchors", "large", "direct")
    ]
    for p in paths:
        verify(p)
