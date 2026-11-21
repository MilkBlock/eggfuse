"""Matched native Pass 3 source audits and rotated resident-slab placement timings."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
groups = run_path(str(HERE.parent / "resident-slab-ablation/study.py"))
source = groups["source"]


def settings(req, args):
    baseline = groups["group"].settings(req, args)["group"]
    spec = dict(baseline["spec_cells"], resident_headers=True, page_width=64)
    return {"off": dict(baseline, spec_cells=spec),
            "dense": dict(baseline, spec_cells=dict(spec, recycle="dense"))}


def observe(arm, report, row, prior):
    row["store"] = report["resident_slabs"]
    row["staging"] = report["spec_cells"]["counts"]
    row["decisions"] = report["single"]["adaptive_rows"]["decision_digest"]
    st, rec = row["store"], row["store"]["recycle"]
    assert st["stats"]["same_fact_buffer"] == st["same_address"] == st["published"] == row["staging"]["used"] > 0
    assert st["pointer_checks"] >= st["old_run_reads"] > 0
    assert st["occupied_slots"] == st["alive"] + st["held_holes"]
    assert rec["new_pages"] == row["staging"]["slabs"]
    if arm == "off":
        assert rec["grants_into_old_holes"] == rec["new_pages_avoided"] == 0
        return
    base = prior["off"]
    for key in ("raw", "commits", "physical", "root_parents", "root_ids", "nested_ids",
                "state_sha", "children", "multi", "wire_hash", "decisions"):
        assert row[key] == base[key], key
    for key in ("granted", "used", "unused", "fresh", "fallback", "requested",
                "redeemed", "private_payload_capacity_bytes", "offers_before_first_verify"):
        assert row["staging"][key] == base["staging"][key], key
    assert rec["new_pages"] + rec["new_pages_avoided"] == base["store"]["recycle"]["new_pages"]
    assert rec["fresh_header_slots"] + rec["grants_into_old_holes"] == st["stats"]["grants"]
    assert rec["grants_into_old_holes"] >= rec["published_from_old_holes"] > 0
    assert rec["empty_runs"] == base["store"]["recycle"]["empty_runs"]
    assert st["alive"] == base["store"]["alive"] and st["old_run_reads"] == base["store"]["old_run_reads"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("exp", "native", "out", "timing"):
        p.add_argument(k, type=Path, nargs="?" if k == "timing" else None)
    p.add_argument("--cases", nargs="+", default=["conjugate-gradient", "3mm"])
    p.add_argument("--repeats", type=int, default=4)
    a = p.parse_args()
    a.seed, a.cap = 1703, 8192
    a.policy = json.loads((HERE.parent / "speculative-allocation-policy/policy.json").read_bytes())
    if a.timing:
        run_path(str(HERE.parent / "verified-binding-transfer/peak.py"))["run"](a, ("off", "dense"), settings)
    else:
        source.study(a, settings, observe, None)
