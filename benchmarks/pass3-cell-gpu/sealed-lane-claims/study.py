"""Measure proof redemption on actual Pass 3 with matched preallocated groups."""
import argparse
import importlib.util
import json
from pathlib import Path

from contract import ENDPOINTS

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("group_study", HERE.parent / "group-named-cells/study.py")
group = importlib.util.module_from_spec(spec)
spec.loader.exec_module(group)
source = group.wave.parent


def arms(req, args):
    cfg = group.settings(req, args)
    return {"off": cfg["off"], "group": cfg["group"], "sealed": dict(cfg["group"], sealed_redemption=1)}


def audit(name, v, q, rows):
    if name == "off":
        return
    q["staging"] = v["spec_cells"]["counts"]
    q["redemption"] = v["root_recipe"]["redemption"]
    assert q["staging"]["redeemed"] == q["staging"]["used"] == q["staging"]["payload_identity"] > 0
    for key in ENDPOINTS:
        assert q[key] == rows["off"][key], (name, key)
    if name == "sealed":
        assert q["staging"] == rows["group"]["staging"]
        r = q["redemption"]
        assert r["fast_accepts"] == r["audit_comparisons"] == r["attempts"] == q["staging"]["used"]
        assert r["content_reads"] == r["fast_denials"] == 0


def faults(a):
    a.out.mkdir(parents=True, exist_ok=False)
    p, plans, req = source.common.config(a, "sum-bits")
    with source.base.session(a.exp / "compact-vanilla-20261121/vanilla-audit", p) as ref:
        gold = ref({"audit": True})
    cfg = arms(req, a)["sealed"]
    report = {}
    with source.base.session(a.native, p, plans) as infer:
        for fault in ("none", "reissued", "unsealed", "foreign", "stale", "duplicate", "withheld"):
            mode = {"reissued": 2, "unsealed": 3}.get(fault, 1)
            voucher_fault = "none" if mode > 1 else fault
            v = infer(dict(cfg, audit=True, sealed_redemption=mode,
                           spec_cells=dict(cfg["spec_cells"], fault=voucher_fault)))
            assert "source_error" not in v, v.get("source_error")
            q = source.base.summarize(v, gold)
            q.pop("work")
            q.pop("rows")
            q["staging"] = v["spec_cells"]["counts"]
            q["redemption"] = v["root_recipe"]["redemption"]
            report[fault] = q
            for key in ENDPOINTS:
                assert report["none"][key] == q[key], (fault, key)
    (a.out / "faults.json").write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("exp", "native", "out"):
        parser.add_argument(key, type=Path)
    parser.add_argument("--faults", action="store_true")
    parser.add_argument("--cases", nargs="+", default=["conjugate-gradient", "3mm"])
    parser.add_argument("--repeats", type=int, default=4)
    args = parser.parse_args()
    args.cap = 8192
    args.seed = 1703
    args.policy = json.loads((HERE.parent / "speculative-allocation-policy/policy.json").read_bytes())
    if args.faults:
        faults(args)
    else:
        source.study(args, arms, audit, None)
