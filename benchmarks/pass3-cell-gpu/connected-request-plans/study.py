"""Exercise checked function requests between two neural parent choices in the actual CPU Pass 3."""
import argparse
import importlib.util
import json
from pathlib import Path
from lower import lower,validate

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("source_study", HERE.parent / "pair-source-frontier/study.py")
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
original = parent.common.config


def extract(program, plans):
    if len(program["recipe"]["rules"])!=len(plans):
        raise ValueError("source and sealed plan rule counts differ")
    out=[]
    for rule,old in zip(program["recipe"]["rules"],plans):
        binding=None
        if old and old["width"]==2:
            original_atoms={i for i,flag,_ in old["ins"] if flag}
            if len(original_atoms)==3:
                schedule=lower(rule)
                if schedule is not None and validate(rule,schedule)==2:
                    head=schedule[:3]
                    if [op for op,_ in head]==["pick","request","pick"] and {i for _,i in head}==original_atoms:
                        a,b,c=[i for _,i in head]
                        if "table" in rule["query"][b]["call"]:
                            binding=[a,b,c]
        out.append(binding)
    return out


def config(args,case):
    p,plans,request=original(args,case)
    args.compiled=extract(json.loads(p.read_bytes()),json.loads(plans.read_bytes()))
    return p,plans,request


def settings(req,args):
    off=dict(req,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
    request=dict(off,connected_requests=args.compiled)
    arms={"off":off,"request":request,"memo":dict(request,bridge_memo=True)}
    if args.directory:
        arms["directory"]=dict(request,bridge_directory=True)
    return arms


def record(arm,out,row,report):
    row["bridge"]=out["multi"]["bridges"]
    if arm!="off":
        assert row["bridge"]["calls"] and row["bridge"]["raw"] and row["bridge"]["found"]
    if arm in ("memo","directory"):
        assert row["raw"]==report["request"]["raw"]


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","conjugate-gradient","3mm","deriche"])
    p.add_argument("--directory",action="store_true")
    p.add_argument("--seed",type=int,default=1703)
    p.add_argument("--repeats",type=int,default=4)
    parent.common.config=config
    args=p.parse_args()
    def finite_control(infer,req,gold,report):
        cfg=settings(req,args)["request"]
        val=infer(dict(cfg,multi_generation="bounded",cap=1000000,audit=True))
        checked=parent.base.summarize(val,gold)
        assert checked["aligned"] and checked["raw"]==report["off"]["raw"]
        assert val["multi"]["bridges"]["calls"]==0
        report["off"]["finite_control_original_digest"]=checked["raw"]
    parent.study(args,settings,record,finite_control)
