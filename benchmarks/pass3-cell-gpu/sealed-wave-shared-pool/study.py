"""Compare four whole-Run demand decisions with actual cross-rule physical reuse."""
import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name, file):
    spec = spec_from_file_location(name, HERE.parent / file)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cross = module("native_pool_study", "cross-rule-cell-pool/study.py")
wave = module("late_demand_study", "wave-demand-policy/study.py")
source = cross.source
MODES = ("entry", "clip", "coverage", "fraction")


def settings(req, a, pool="shared"):
    cross.configurations(req, a)  # read the exact compiler fact widths
    cfg = wave.settings(req, a)
    return {name: value if name=="off" else dict(value,spec_cells=dict(value["spec_cells"],cross_pool=pool))
            for name,value in cfg.items()}


def audit(name, native, row, rows, args, shared=True):
    if name=="off":
        return
    spec = native["spec_cells"]
    row["pool"] = p = spec["pool"]
    row["demand"] = d = spec["wave_demand"]
    row["staging"] = s = spec["counts"]
    row["seal"] = sig = native["root_recipe"]["redemption"]
    bounds,row["run_layout_sha256"] = cross.overlaps(spec,args.widths)
    for key,expected in bounds.items():
        assert p[key]==expected,(name,key)
    assert p["layout_bound" if shared else "rule_bound"] == s["used"] == sig["audit_comparisons"] == sig["fast_accepts"]
    assert s["used"] == p["own"] + p["borrowed"] == s["payload_identity"]
    assert s["used"]+s["unused"]==s["granted"]==s["slots_before_first_verify"]
    assert s["used"]+s["fallback"]==s["fresh"]
    assert s["offers_after_first_verify"]==s["slots_after_first_verify"]==p["rejected_layout"]==0
    for field in cross.sealed.ENDPOINTS:
        assert row[field]==rows["off"][field],(name,field)
    if name!="entry":
        assert d["post_issue_grants"]==s["granted"] and d["excess_at_issue"]==0
        assert p["from_inactive_donors"]==0 and p["layout_bound"]==p["offered_layout_bound"]
        if name!="clip":
            assert d["predictions"]==d["nonempty_rules"]>0


def paired(a):
    """Evaluate matching per-rule/native storage and negative controls outside timing."""
    a.out.mkdir(parents=True,exist_ok=False)
    output={}
    for case in a.cases+["sum-bits"]:
        program,plans,req=source.common.config(a,case)
        with source.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as exact:
            gold=exact({"audit":True})
        paired={}
        with source.base.session(a.native,program,plans) as infer:
            if case=="sum-bits":
                native=settings(req,a)["coverage"]
                for fault in ("none","layout","other-rule","reissued","stale","duplicate"):
                    cfg=dict(native["spec_cells"])
                    if fault=="layout":cfg["cross_pool"]="bad-layout"
                    if fault in ("other-rule","stale","duplicate"):cfg["fault"]=fault
                    v=infer(dict(native,spec_cells=cfg,audit=True,sealed_redemption=2 if fault=="reissued" else 1))
                    q=source.base.summarize(v,gold)
                    assert q["aligned"] and all(q["checks"].values())
                    ledgers={k:q[k] for k in cross.sealed.ENDPOINTS}
                    if fault!="none":
                        assert ledgers==paired["none"]["ledgers"]
                    paired[fault]=dict(ledgers=ledgers,counts=v["spec_cells"]["counts"],pool=v["spec_cells"]["pool"],
                                       seal=v["root_recipe"]["redemption"],checks=q["checks"])
            else:
                cfgs=settings(req,a,"per-rule")
                v=infer(dict(cfgs["off"],audit=True))
                baseline=source.base.summarize(v,gold)
                for name in MODES:
                    v=infer(dict(cfgs[name],audit=True))
                    q=source.base.summarize(v,gold)
                    assert q["aligned"] and all(q["checks"].values())
                    audit(name,v,q,{"off":baseline},a,False)
                    paired[name]=dict(pool=q["pool"],staging=q["staging"],seal=q["seal"],checks=q["checks"],
                                      ledgers={k:q[k] for k in cross.sealed.ENDPOINTS},run_layout_sha256=q["run_layout_sha256"])
        output[case]=paired
        (a.out/"paired.json").write_text(json.dumps(output,indent=1)+"\n")
        print(case,"matched",list(paired),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out"):
        parser.add_argument(key,type=Path)
    parser.add_argument("--paired",action="store_true")
    a=parser.parse_args()
    a.seed=1703
    a.cap=8192
    a.repeats=4
    a.cases=["conjugate-gradient","3mm"]
    a.modes=MODES[1:]
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.heads=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]
    if a.paired:
        paired(a)
    else:
        source.study(a,settings,lambda *fields:audit(*fields,a),None)
