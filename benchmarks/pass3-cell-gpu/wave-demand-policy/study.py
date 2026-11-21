"""Measure one forecast per rule on the sealed wave before exact validation."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("group_study", HERE.parent / "group-named-cells/study.py")
group = importlib.util.module_from_spec(spec)
spec.loader.exec_module(group)
source = group.wave.parent
MODES = ("delay", "clip", "balanced", "coverage", "fraction")
KEYS = ("rhs", "raw", "multi", "single_winners", "multi_winners", "root_ids", "nested_ids",
        "root_parents", "commits", "children", "physical", "wire_hash", "state_sha", "score")


def settings(req, args):
    original = group.settings(req, args)
    early = dict(original["group"], sealed_redemption=1)
    arms = {"off": original["off"], "entry": early}
    for mode in args.modes:
        option = {"mode": mode}
        if mode in args.heads:
            option = dict(mode="fraction" if mode == "fraction" else "count", weights=args.heads[mode])
        arms[mode] = dict(early, spec_cells=dict(early["spec_cells"], wave_demand=option))
    return arms


def observe(name, v, row, rows):
    row["score"] = v["single"]["adaptive_rows"]["decision_digest"]
    if name == "off":
        return
    row["staging"] = c = v["spec_cells"]["counts"]
    row["demand"] = d = v["spec_cells"]["wave_demand"]
    row["seal"] = v["root_recipe"]["redemption"]
    assert all(row[key] == rows["off"][key] for key in KEYS)
    assert c["offers_after_first_verify"] == c["slots_after_first_verify"] == 0
    assert row["seal"]["fast_accepts"] == c["payload_identity"] == c["used"] > 0
    assert c["used"] + c["unused"] == c["granted"]
    assert c["used"] + c["fallback"] == row["root_allocated"]
    if name != "entry":
        assert 0 < d["batches"] <= c["runs"]
        assert d["post_issue_grants"] == c["granted"]
        assert 0 < d["nonempty_rules"] <= d["active_rules"]
        assert d["min_demand_bound"] >= c["used"]
        if name != "delay":
            assert d["excess_at_issue"] == 0
        if name not in ("clip", "delay"):
            assert d["predictions"] == d["nonempty_rules"]


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("exp", "native", "out"):
        p.add_argument(name, type=Path)
    p.add_argument("--cases", nargs="+", default=["conjugate-gradient", "3mm"])
    p.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    p.add_argument("--seed", type=int, default=1703)
    p.add_argument("--cap", type=int, default=8192)
    p.add_argument("--repeats", type=int, default=4)
    a = p.parse_args()
    a.policy = json.loads((HERE.parent / "speculative-allocation-policy/policy.json").read_bytes())
    a.heads = json.loads((HERE / "policy.json").read_bytes())["models"]
    return a


if __name__ == "__main__":
    source.study(arguments(), settings, observe, None)
