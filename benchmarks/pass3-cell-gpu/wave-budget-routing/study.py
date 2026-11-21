"""Matched CG and 3mm physical budgets, native source execution, receipt and ceiling audits."""
import argparse
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
parent = run_path(str(HERE.parent / "wave-demand-policy/study.py"))
group = parent["group"]
source = parent["source"]
MODES = ("original", "offers", "clip", "fraction", "coverage")
FAULTS = ("none", "reissued", "unsealed", "foreign", "stale", "duplicate", "withheld")


def settings(req, args):
    base = group.settings(req, args)["group"]
    entry = dict(base, sealed_redemption=1,
                 spec_cells=dict(base["spec_cells"], layout_routing={"mode": "original"}))
    result = {"off": entry}
    for name in MODES:
        route = {"mode": name}
        if name in ("coverage", "fraction"):
            route = {"mode": "count" if name == "coverage" else name, "weights": args.heads[name]}
        result[name] = dict(entry, spec_cells=dict(entry["spec_cells"], wave_demand={"mode":"delay"},
                                                  layout_routing=route))
    return result


def summarize(spec, fault=False):
    digest = hashlib.sha256()
    class_oracle = offers_bound = hit = moved = 0
    class_totals = [0]*4
    for epoch, original, real, offers, fresh, potential, published, redirected in spec["layout_runs"]:
        assert original == real
        assert all(f <= o for f, o in zip(fresh, offers))
        bound = sum(min(n,f) for n,f in zip(original,fresh))
        assert bound >= potential >= published
        if not fault:
            assert potential == published
        digest.update(json.dumps([epoch, real, offers, fresh], separators=(",", ":")).encode()+b"\n")
        for i, n in enumerate(real):
            class_totals[i] += n
        class_oracle += bound
        offers_bound += sum(min(n,o) for n,o in zip(original,offers))
        hit += published
        moved += redirected
    assert len(spec["layout_runs"]) == spec["counts"]["runs"]
    assert hit == spec["counts"]["used"] and sum(class_totals) == spec["counts"]["granted"]
    return dict(runs=len(spec["layout_runs"]), source_budget_sha=digest.hexdigest(),
                grants=class_totals, class_oracle=class_oracle, offers_bound=offers_bound,
                actual=hit, moved=moved, quiet_runs=spec["quiet_runs"])


def observe(name, v, row, prior):
    row["score"] = v["single"]["adaptive_rows"]["decision_digest"]
    spec = v["spec_cells"]
    row["route"] = route = summarize(spec)
    row["staging"] = c = spec["counts"]
    row["seal"] = seal = v["root_recipe"]["redemption"]
    assert c["offers_after_first_verify"] == c["slots_after_first_verify"] == 0
    assert seal["fast_accepts"] == seal["audit_comparisons"] == c["used"] == c["payload_identity"] > 0
    if name=="off":
        return
    base = prior["off"]
    assert all(base[k] == row[k] for k in parent["KEYS"])
    for k in ("runs","class_oracle","offers_bound","grants","source_budget_sha"):
        assert route[k] == base["route"][k], (name,k)
    for k in ("header_capacity_bytes","private_payload_capacity_bytes","preconstructed","granted",
              "offers","fresh","requested","clipped","slabs","peak_private_bytes"):
        assert c[k] == base["staging"][k], (name,k)
    if name=="original":
        assert c["used"] == base["staging"]["used"]
    else:
        assert route["moved"] > 0


def fault_trials(a):
    a.out.mkdir(parents=True,exist_ok=False)
    program, plans, req = source.common.config(a,"sum-bits")
    with source.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as oracle:
        gold=oracle({"audit":True})
    report={}
    with source.base.session(a.native,program,plans) as infer:
        cfg=settings(req,a)["fraction"]
        for name in FAULTS:
            mode={"reissued":2,"unsealed":3}.get(name,1)
            fault="none" if mode>1 else name
            v=infer(dict(cfg,audit=True,sealed_redemption=mode,spec_cells=dict(cfg["spec_cells"],fault=fault)))
            q=source.base.summarize(v,gold)
            q.pop("work");q.pop("rows")
            q["route"]=summarize(v["spec_cells"], True)
            q["staging"]=v["spec_cells"]["counts"];q["seal"]=v["root_recipe"]["redemption"]
            report[name]=q
            assert q["aligned"] and all(q["checks"].values())
            if name!="none":
                for k in parent["KEYS"]:
                    if k!="score":assert q[k]==report["none"][k],(name,k)
                assert q["route"]["source_budget_sha"]==report["none"]["route"]["source_budget_sha"]
            if name in ("unsealed","reissued","stale","foreign","withheld"):
                assert q["staging"]["used"]==0
            if name=="duplicate":
                assert q["staging"]["duplicate_denials"]==q["staging"]["used"]==report["none"]["staging"]["used"]
    (a.out/"faults.json").write_text(json.dumps(report,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","out"):p.add_argument(name,type=Path)
    p.add_argument("--cases",nargs="+",default=["conjugate-gradient","3mm"])
    p.add_argument("--faults",action="store_true")
    p.add_argument("--repeats",type=int,default=4)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.heads=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]
    if a.faults:fault_trials(a)
    else:source.study(a,settings,observe,None)
