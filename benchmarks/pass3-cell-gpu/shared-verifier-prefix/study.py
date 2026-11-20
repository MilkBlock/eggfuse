"""Measure cross-rule validation on independently issued neural tokens in actual Cell CPU Pass 3."""
import argparse
import json
from statistics import median
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=spec_from_file_location("source_study",HERE.parent/"pair-source-frontier/study.py")
base=module_from_spec(spec)
spec.loader.exec_module(base)

MODES={"off":0, "anchor":1, "prefix":2, "sibling":3, "negative":4, "live":5}

def settings(req,args):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    return {name:dict(off,shared_prefix=mode) for name,mode in MODES.items()}

def record(arm,output,row,report):
    single=output["single"]
    row["family"]=single["adaptive_rows"]["family"]
    row["single_work"]=single["work"]
    row["decisions"]=single["adaptive_rows"]["decision_digest"]
    if arm!="off":
        assert row["family"]["hits"]>0
        assert row["family"]["hits"]==row["family"]["audit_checks"]
        for name in ("raw","physical","commits","multi","children","cells","decisions"):
            assert row[name]==report["off"][name],(arm,name)

def profile(args):
    args.out.mkdir(parents=True,exist_ok=False)
    summary={}
    for case in args.cases:
        program,plan,req=base.common.config(args,case)
        configs=settings(req,args)
        with base.base.session(args.exp/"compact-vanilla-20261121/vanilla",program) as native:
            gold=native({})
        arms=("off","prefix","live")
        samples={k:[] for k in arms}
        with base.base.session(args.native,program,plan) as infer:
            for rep in range(args.repeats+1):
                names=list(samples)
                names=names[rep%len(names):]+names[:rep%len(names)]
                for name in names:
                    cfg=configs[name]
                    v=infer(dict(cfg,rows=dict(cfg["rows"],profile=True)))
                    assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"]
                    if rep:
                        ns=v["single"]["adaptive_rows"]["phase_ns"]
                        samples[name].append([*[t/1e6 for t in ns],v["ms"]])
        summary[case]={k:dict(samples=t,ms=list(map(median,zip(*t)))) for k,t in samples.items()}
        (args.out/"phases.json").write_text(json.dumps(summary,indent=1)+"\n")
        print(case,{k:round(v["ms"][3],2) for k,v in summary[case].items()},flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","out"):
        p.add_argument(name,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--seed",type=int,default=1703)
    p.add_argument("--repeats",type=int,default=4)
    p.add_argument("--profile",action="store_true")
    args=p.parse_args()
    if args.profile:profile(args)
    else:base.study(args,settings,record,None)
