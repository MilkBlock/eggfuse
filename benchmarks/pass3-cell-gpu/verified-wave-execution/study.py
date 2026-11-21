"""Charge proof filtering, survivor queues, optional positive ports and shared allocation together."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
group=run_path(str(HERE.parent/"group-named-cells/study.py"))
negative=run_path(str(HERE.parent/"single-pivot-certificates/study.py"))
source=group["wave"].parent


def settings(req,a):
    original=group["settings"](req,a)
    off=original["off"]
    filtered=dict(off,rows=dict(off["rows"],scalar_certificates=True))
    packed=dict(filtered,packed_single=True)
    ports=dict(packed,rows=dict(packed["rows"],scalar_handoff=True))
    spec=dict(original["group"]["spec_cells"],cross_pool="shared",
              wave_demand=dict(mode="fraction",weights=a.fraction))
    return {"off":off,"filter":filtered,"packed":packed,"ports":ports,
            "pool":dict(ports,spec_cells=spec,sealed_redemption=1)}


def observe(arm,v,q,rows):
    single=v["single"]
    ranking=single["adaptive_rows"]
    counts=ranking["scalar_certificates"]
    q.update(full_single=negative["digest"](single["committed"]),decisions=ranking["decision_digest"],
             complete_scores=single["work"][:2],emitted=ranking["stats"]["emitted"],verified=single["work"][2],
             omitted=sum(c["missing"]+c["stale"] for c in counts),audited=sum(c["audited"] for c in counts),
             transfers=ranking["point_transfers"],queue=single["packed"],neural_events=v["multi"]["wave"])
    if arm=="off":
        return
    base=rows["off"]
    for k in negative["ALIGN"]:
        assert q[k]==base[k],(arm,k)
    assert q["audited"]==q["omitted"]>0
    assert q["complete_scores"]==base["complete_scores"]
    assert q["verified"]+q["omitted"]==base["verified"]
    assert q["emitted"]+q["omitted"]==base["emitted"]
    if arm!="filter":
        ref=rows["filter"]
        for k in ("raw","wire_hash","wire_bytes","commits","physical","verified","emitted","omitted","neural_events"):
            assert q[k]==ref[k],(arm,k)
        assert q["queue"]["lanes"]==q["emitted"]>0 and q["queue"]["pending_bytes"]==0
    if arm in ("ports","pool"):
        assert 0<q["transfers"][0]==q["transfers"][1]
    if arm=="pool":
        spec=v["spec_cells"]
        p=q["pool"]=spec["pool"]
        c=q["storage"]=spec["counts"]
        assert p["borrowed"]>0 and p["own"]+p["borrowed"]==c["used"]==p["layout_bound"]
        assert c["used"]==v["root_recipe"]["redemption"]["fast_accepts"]==c["payload_identity"]
        assert c["slots_after_first_verify"]==c["offers_after_first_verify"]==0


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):
        parser.add_argument(k,type=Path)
    parser.add_argument("--cases",nargs="+",default=["sum-bits","dot-product","conjugate-gradient","3mm","deriche"])
    parser.add_argument("--seed",type=int,default=1703)
    parser.add_argument("--repeats",type=int,default=4)
    a=parser.parse_args()
    a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    source.study(a,settings,observe,None)
