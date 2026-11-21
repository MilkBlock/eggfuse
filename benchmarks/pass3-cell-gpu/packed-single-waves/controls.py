"""Compare the two wire representations on denied and replayed storage claims."""
import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
driver = run_path(str(HERE/"study.py"))
source = driver["source"]


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    prog, plan, req = source.common.config(a,"sum-bits")
    arms = driver["settings"](req,a)
    with source.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as ref:
        gold = ref({"audit":True})
    results = {}
    with source.base.session(a.native,prog,plan) as infer:
        for fault in ("none","withheld","duplicate","foreign","stale"):
            pair = {}
            for mode in ("group","packed_group"):
                arm = arms[mode]
                v = infer(dict(arm, audit=True, spec_cells=dict(arm["spec_cells"],fault=fault)))
                q = source.base.summarize(v,gold)
                assert q["aligned"] and all(q["checks"].values())
                c = v["spec_cells"]["counts"]
                raw = [q[k] for k in driver["KEYS"] if k not in ("decision","wave")]
                raw += [v["single"]["adaptive_rows"]["decision_digest"], v["multi"]["wave"]]
                pair[mode] = {"digest": hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),
                              "used": c["used"],"duplicates": c["duplicate_denials"]}
            assert pair["group"]==pair["packed_group"]
            row = results[fault] = pair["packed_group"]
            assert row["digest"] == results["none"]["digest"]
            if fault in ("withheld","foreign","stale"):
                assert row["used"]==0
            if fault=="duplicate":
                assert row["duplicates"]==row["used"]==results["none"]["used"]>0
    (a.out/"controls.json").write_text(json.dumps(results,indent=1)+"\n")
    print("Checked both representations for original, withheld, stale, wrong and duplicate claims.")


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):
        p.add_argument(k,type=Path)
    a=p.parse_args()
    a.seed=1703
    a.cap=8192
    a.staged=True
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    run(a)
