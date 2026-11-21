"""Measure effective constructor births per external neural packet under score and width policies."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
source=driver["source"]
arms=("expanded","baseline","view1","view2","view3","row4","rl-small","rl-large")


def configure(req,a,name):
    cfg=driver["settings"](req,a)["packed"]
    row=cfg["rows"].copy()
    if name=="expanded":
        row["scalar_certificates"]=False
    if name=="row4":
        row.update(action=6,max_rows=4)
    if name.startswith("rl-"):
        h=2 if name=="rl-small" else 32
        checkpoint=a.checkpoints[f"1703-policy-gradient-{h}-8.json"]
        row.pop("action")
        row.update(policy=checkpoint["weights"],max_rows=8)
    views={"view1":1,"view3":3}.get(name,2)
    if name.startswith("view"):
        # The two-view-only tier specialization must not confound the signature comparison.
        cfg.pop("tiered_ports",None)
    cfg["multi_mode"]=cfg["multi_mode"].replace("2xlearned",{1:"learned",2:"2xlearned",3:"3xlearned"}[views])
    return dict(cfg,rows=row)


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def audit(v,gold,plain,truth):
    assert "source_error" not in v,v.get("source_error")
    q=source.base.summarize(v,gold)
    assert q["aligned"] and all(q["checks"].values())
    report=v["constructor_births"]
    born=report["rows"]
    seen=set()
    roots={r[2]:r for r in v["root_recipe"]["commits"]}
    assert len(roots)==q["rhs"]==q["neural_rhs"]
    events=[e for e in born if e[7]&1]
    for e in events:
        assert e[0] not in seen
        seen.add(e[0])
        assert e[4]==0 or roots[e[4]][5]==e[2]
    assert truth==[(e[0],e[1]) for e in events]
    assert report["endpoint"]==plain["endpoint"] and report["coalesced"]==plain["coalesced"]
    visible={f for f,_,hidden in report["endpoint"] if not hidden}
    n=sum(bool(e[3] and e[4]) for e in events)
    retained=sum(bool(e[3] and e[4] and e[0] in visible) for e in events)
    denom=v["multi"]["wave"]
    m=denom["sealed_multi"];s=denom["sealed_single"]
    child=sum(c["selected"] for c in v["merge_child"]["issued"])
    return dict(runs=v["runs"],rhs=q["rhs"],source=q["state_sha"],checks=q["checks"],
                root_ids=q["root_ids"],nested_ids=q["nested_ids"],birth_digest=digest(truth),
                constructor_births=n,unowned=sum(bool(e[3] and not e[4]) for e in events),
                tokens=[s,m,child],per_root=n/(s+m),per_packet=n/(s+m+child),per_commit=n/len(roots),
                retained_origins=retained,effective_per_root=retained/(s+m),effective_per_packet=retained/(s+m+child),
                row_calls=v["single"]["adaptive_rows"]["stats"]["calls"],pages=v["single"]["packed"]["pages"],
                views=v["multi"]["embedding_views"],decisions=v["single"]["adaptive_rows"]["decision_digest"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ("exp","native","out"):
        p.add_argument(x,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--arms",nargs="+",default=arms,choices=arms)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    a.checkpoints=json.loads((HERE.parent/"adaptive-row-policy/checkpoints.json").read_bytes())
    results={}
    for c in a.cases:
        prog,plans,req=source.common.config(a,c)
        with source.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as oracle:
            gold=oracle({"audit":True})
        with source.base.session(a.native,prog,plans) as exact:
            control=exact({"audit":True,"baseline":True,"birth_ledger":True})
            assert control["state_sha"]==gold["state_sha"] and control["runs"]==gold["runs"]
            plain=control["constructor_births"]
            truth=[(e[4],e[1]) for run in control["events"] for e in run if e[0]=="birth"]
            del control
        records=results[c]={}
        for name in a.arms:
            with source.base.session(a.native,prog,plans) as infer:
                v=infer(dict(configure(req,a,name),audit=True,birth_ledger=True))
            info=audit(v,gold,plain,truth)
            records[name]=info;del v
            (a.out/"results.json").write_text(json.dumps(results,indent=1)+"\n")
            print(c,name,info["tokens"],info["constructor_births"],info["per_root"],flush=True)

if __name__=="__main__":
    main()
