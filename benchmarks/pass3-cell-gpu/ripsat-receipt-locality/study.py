"""Measure receiver work and Run semantics when stale named receipts are excluded early."""
import argparse
from pathlib import Path
from runpy import run_path
from statistics import median
import json

HERE=Path(__file__).resolve().parent
matrix=run_path(str(HERE.parent/"ripsat-publication-matrix/study.py"))
src=matrix["src"]
MODES=("all","early","indexed")


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    data={}
    for case in a.cases:
        p,plans,req=src.config(a,case)
        variants,_=matrix["libraries"](a.exp,p,case)
        plan=variants["ripsat"]
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",p) as ref:
            gold=ref({"audit":True})
        settings={k:dict(plan,receipt_scan=i) for i,k in enumerate(MODES)}
        arms={}
        sets={}
        for name,opts in settings.items():
            with src.base.session(a.native,p,plans) as get:
                v=get(matrix["cfg"](req,opts,True))
            q,latest=matrix["summarize"](v,gold,True)
            sets[name]=latest
            q["scan"]=v["strict_named"]["receipt_scan"]
            q["scope"]=v["strict_named"]["counts"]
            q["ms"]=[];q["profile"]=[]
            if name!="all":
                for field in (*matrix["FIXED"],"emitted","internal","set_internal","fept","signed_ordinals_sha","terminal_ordinals_sha"):
                    assert q[field]==arms["all"][field],(case,name,field)
                assert latest==sets["all"]
            arms[name]=q
        with src.base.session(a.native,p,plans) as get:
            for lap in range(a.repeats+1):
                seq=MODES[lap%3:]+MODES[:lap%3]
                for name in seq if lap%2 else reversed(seq):
                    v=get(matrix["cfg"](req,settings[name]))
                    assert v["runs"]==gold["runs"] and v["state_sha"]==gold["state_sha"]
                    assert v["root_recipe"]["emitted"]==arms[name]["emitted"]
                    w=v["strict_named"]["receipt_scan"]
                    assert not w["profile"] and w["receiver_ns"]==w["index_ns"]==0
                    if lap:arms[name]["ms"].append(v["ms"])
            for lap in range(4):
                seq=MODES[lap%3:]+MODES[:lap%3]
                for name in seq:
                    v=get(matrix["cfg"](req,dict(settings[name],receipt_profile=True)))
                    assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"]
                    work=v["strict_named"]["receipt_scan"]
                    assert work["profile"] and work["receiver_ns"]>0
                    if lap:arms[name]["profile"].append(work)
            faults={}
            for fault in ("missing","stale","wrong_fields"):
                v=get(matrix["cfg"](req,dict(settings["indexed"],set_fault=fault)))
                if fault=="wrong_fields":
                    msg=v.get("source_error");assert msg
                    faults[fault]=dict(message=msg,runs=v["runs"])
                else:
                    assert v["runs"]==gold["runs"] and v["state_sha"]==gold["state_sha"]
                    assert v["strict_named"]["set_publication"]["confirmed"]==0
                    faults[fault]=dict(runs=v["runs"],source=v["state_sha"],emitted=v["root_recipe"]["emitted"])
        for q in arms.values():q["median_ms"]=median(q["ms"])
        data[case]=dict(arms=arms,faults=faults)
        (a.out/"results.json").write_text(json.dumps(data,indent=1)+"\n")
        print(case,[(k,v["scan"]["row_reads"],round(v["median_ms"],2),
                     round(median(r["receiver_ns"]+r["index_ns"] for r in v["profile"])/1e6,3)) for k,v in arms.items()],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","out"):parser.add_argument(key,type=Path)
    parser.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    parser.add_argument("--repeats",type=int,default=5)
    run(parser.parse_args())
