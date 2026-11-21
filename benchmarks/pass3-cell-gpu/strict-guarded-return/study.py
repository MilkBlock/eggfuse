"""Execute statically bound child predicates on the producer's actual returned FactRef."""
import argparse
from collections import Counter
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
partial=run_path(str(HERE.parent/"strict-partial-named-ports/study.py"))
base=partial["driver"]
strict=partial["strict"]


def analyze(v,gold):
    assert "source_error" not in v,v.get("source_error")
    q=strict.src.base.summarize(v,gold)
    assert q["aligned"] and all(q["checks"].values())
    receipt=v["strict_named"] or {}
    links={s:(root,path,ports,run) for s,root,path,ports,run in receipt.get("signed_commits",[])}
    emitted=v["root_recipe"]["emitted"]
    winners={r[2]:r for r in v["root_recipe"]["commits"]}
    end={f for f,_,hidden in v["constructor_births"]["endpoint"] if not hidden}
    paid={r["allocated"]<<32 for r in v["merge_child"]["issued"] if r["allocated"] is not None}
    by_consumer={}
    for serial,(root,path,ports,run) in links.items():
        assert root in winners and root not in links and serial in winners and winners[serial][3]==path[-1][-1]
        assert all(edge[1]==port[1] for edge,port in zip(path,ports))
        assert winners[serial][5]>winners[root][5]
        by_consumer.setdefault(winners[serial][3],Counter())["commits"]+=1
    born=visible=0
    for f,t,e,k,serial,_,_,flags in v["constructor_births"]["rows"]:
        if not (k and serial and flags&1):continue
        born+=1;visible+=int(f in end)
        if serial in links:
            cat="separately_paid" if f in paid else "dynamic" if flags&2 else "typed"
            totals=by_consumer[winners[serial][3]]
            totals[cat+"_births"]+=1;totals[cat+"_visible"]+=int(f in end)
    child=v["merge_child"]["counts"][1]
    count=sum(emitted)+child
    return dict(runs=v["runs"],rhs=q["rhs"],source=q["state_sha"],checks=q["checks"],physical=q["physical"],parents=q["root_parents"],
                ids=q["root_ids"],nested=q["nested_ids"],commits=q["commits"],children=q["children"],scores=v["single"]["adaptive_rows"]["decision_digest"],
                packets=count,emitted=emitted,child=child,born=born,visible=visible,fept=visible/count,internal=len(links),
                rules=by_consumer,guard_rules=receipt.get("guard_rules",[]),guard_counts=receipt.get("guard_counts",[0,0,0]),ms=[])


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    output={}
    for case in a.cases:
        p,plan,req=strict.src.config(a,case)
        configs={"leaf":dict(depth=0),"plain":dict(depth=1,partial=True),"guarded":dict(depth=1,partial=True,value_guards=True),
                 "two":dict(depth=2,partial=True,value_guards=True)}
        with strict.src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",p) as ref:gold=ref({"audit":True})
        rows={}
        for name,opts in configs.items():
            cfg=base["filtered"](req,dict(opts,record_links=True))
            with strict.src.base.session(a.native,p,plan) as get:
                v=get(dict(cfg,birth_ledger=True,audit=True))
                q=analyze(v,gold)
                if name!="leaf":
                    root=rows["leaf"]
                    for field in ("rhs","runs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child"):
                        assert q[field]==root[field],(case,name,field)
                    assert root["packets"]-q["packets"]==q["internal"]
                rows[name]=q
                print(case,name,q["internal"],q["guard_counts"],q["fept"],flush=True)
        with strict.src.base.session(a.native,p,plan) as get:
            names=list(configs)
            for lap in range(a.repeats+1):
                for n in names[lap%len(names):]+names[:lap%len(names)]:
                    v=get(base["filtered"](req,configs[n]))
                    assert v["root_recipe"]["emitted"]==rows[n]["emitted"] and v["state_sha"]==gold["state_sha"]
                    if n!="leaf":
                        actual=v["strict_named"]["counts"]
                        assert actual["source_commits"]==rows[n]["internal"] and actual["audit_score_inputs"]==0
                    if lap:rows[n]["ms"].append(v["ms"])
            fail=get(base["filtered"](req,dict(configs["guarded"],wrong_port=True)))
            assert "strict named return port corruption" in fail.get("source_error","")
        output[case]={"arms":rows,"corruption_rejected_at_run":fail["runs"]}
        (a.out/"results.json").write_text(json.dumps(output,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--repeats",type=int,default=3)
    run(p.parse_args())
