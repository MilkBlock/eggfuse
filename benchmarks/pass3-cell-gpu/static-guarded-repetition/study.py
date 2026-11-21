"""Compare fixed static depths with fresh root and source identity accounting."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
guard=run_path(str(HERE.parent/"strict-guarded-return/study.py"))
src=guard["strict"].src


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        prog,plans,req=src.config(a,case)
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as get:gold=get({"audit":True})
        arms={};configs={}
        for depth in (0,2,4,8):
            opts=dict(depth=depth,partial=True,value_guards=True,repeat=True)
            configs[depth]=guard["base"]["filtered"](req,opts)
            with src.base.session(a.native,prog,plans) as get:
                v=get(dict(configs[depth],strict_named=dict(opts,record_links=True),audit=True,birth_ledger=True))
            q=guard["analyze"](v,gold)
            named=v["strict_named"] or {}
            q["compiled_repeat_ops"]=named.get("compiled_repeat_ops",[]);q["depths"]=named.get("commits_by_depth",{})
            origins={x[0] for x in v["constructor_births"]["endpoint"] if not x[2]}
            paid={r["allocated"]<<32 for r in v["merge_child"]["issued"] if r["allocated"] is not None}
            mapping={s:d for s,_,d in named.get("links",[])}
            typed={}
            for f,t,e,k,serial,_,_,flags in v["constructor_births"]["rows"]:
                if not(k and flags&1) or flags&2 or f in paid or f not in origins or serial not in mapping:continue
                i=mapping[serial];typed[i]=typed.get(i,0)+1
            q["typed_visible_by_depth"]=typed
            assert sum(typed.values())==sum(v.get("typed_visible",0) for v in q["rules"].values())
            if depth:
                assert len(mapping)==sum(q["depths"].values())==arms[0]["packets"]-q["packets"]
                assert all(q[k]==arms[0][k] for k in ("rhs","runs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child"))
                assert all(int(d)<=depth for d in q["depths"])
            arms[depth]=q;del v
            print(case,depth,q['packets'],q['fept'],q['depths'],typed,flush=True)
        names=list(arms)
        with src.base.session(a.native,prog,plans) as get:
            for i in range(a.repeats+1):
                for d in names[i%len(names):]+names[:i%len(names)]:
                    v=get(configs[d]);q=arms[d]
                    assert v["state_sha"]==q["source"] and v["root_recipe"]["emitted"]==q["emitted"]
                    if d:assert v["strict_named"]["counts"]["source_commits"]==q["internal"]
                    if i:q["ms"].append(v["ms"])
        data[case]=arms;(a.out/"results.json").write_text(json.dumps(data,indent=1)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--repeats",type=int,default=3)
    run(p.parse_args())
