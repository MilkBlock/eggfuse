"""Check the denominators, assignment work, real participation, recurrent decisions and training split."""

import json
from pathlib import Path
from statistics import median


def check(folder):
    def read(name):
        return json.loads((folder / (name + ".json")).read_text())

    width, policy, page, verification, larger, integrated, holdout = map(
        read,
        (
            "width",
            "policy",
            "pages",
            "verification",
            "larger",
            "integrated",
            "large-integrated",
        ),
    )
    assert len(width) == 4 and len(policy) == len(page) == len(verification) == 16
    assert len(larger) == 2 and len(integrated) == 8 and len(holdout) == 4
    pre = read("prefilter")
    for table in (width, policy, page, verification, larger, integrated, holdout, pre):
        for key, record in table.items():
            assert (
                record["neural"] * 100 >= 98 * record["rhs"]
                and record["direct"] * 100 >= 98 * record["fresh_cells"]
            )
            if key.endswith("certified"):
                assert record["neural"] == record["rhs"]
            for arm, v in record["arms"].items():
                assert len(v["ms"]) >= 4 and v["median_ms"] == median(v["ms"])
                if "evaluations" not in v or arm == "native":
                    continue
                assert (
                    sum(v["calls"]) == v["invocations"]
                    and sum(v["addressed"]) == v["source_headers"]
                )
                assert v["evaluations"] <= v["source_headers"]
                if arm.startswith("prefilter"):
                    assert v["semantic"] == record["semantic"]
                    meets = (
                        100 * v["neural"] >= 98 * record["rhs"]
                        and 100 * v["direct"] >= 98 * record["fresh_cells"]
                    )
                    assert v["meets_coverage"] == meets
    assert len(pre) == 16
    for record in pre.values():
        base = record["arms"]["verify-2"]
        empty = record["arms"]["prefilter-1"]
        frontier = record["arms"]["prefilter-2"]
        assert empty["proof_empty_calls"] > 0 and frontier["proof_stale_headers"] > 0
        assert (
            frontier["source_headers"]
            < empty["source_headers"]
            <= base["source_headers"]
        )
    for sample in read("heldout-cost").values():
        assert sample["size_quantiles"][-1] > 245
        for left, block in sample["bins"].items():
            assert sum(block["fastest"]) == block["n"]
            if int(left) > 1:
                assert block["fastest"][0] + block["fastest"][4] == block["n"]
    for r in width.values():
        a = r["arms"]
        assert (
            a["shared-8"]["real_parallel_calls"] > 0
            and a["shared-8"]["peak_workers"] >= 2
        )
        assert (
            a["serial-8"]["real_parallel_calls"]
            == a["shared-1"]["real_parallel_calls"]
            == 0
        )
        assert a["direct-1"]["evaluations"] == a["direct-1"]["source_headers"]
        assert a["shared-1"]["evaluations"] < a["direct-1"]["evaluations"]
    for r in verification.values():
        a = r["arms"]
        assert a["verify-2"]["verification"]["pruned_by_suffix"] > 0
        assert a["verify-4"]["verification"]["cache_resets"] > 0
    for r in page.values():
        assert r["arms"]["page-1"]["wire_bytes"] < r["arms"]["shared-1"]["wire_bytes"]
    for key, d in read("controls").items():
        for k, r in d.items():
            assert r["state"] == d["full/use"]["state"]
            if not k.endswith("/use"):
                assert r["allocated"] == r["applied"] == 0
    weights = read("checkpoints")
    for w in weights.values():
        assert w["params"] == 14 * w["size"] + 8 and w["params"] in (36, 120, 456)
        assert set(w["programs"]) == set(read("training-summary")["programs"])
        assert "jacobi-1d" not in w["programs"] and "sum-bits" not in w["programs"]
    print(
        "Verified adaptive CPU row placements, trained capacities, latency samples, immutable proofs and held-out programs."
    )


if __name__ == "__main__":
    check(Path(__file__).resolve().parent)
