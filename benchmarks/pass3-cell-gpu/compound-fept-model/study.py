"""Measure true forward FEPT, additional decision denominators and source receipts in a single binary."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
wide=run_path(str(HERE.parent/"wide-fept-composition/study.py"))
src=wide["src"]


def settings(req,a,trace=False):
    orig=wide["settings"](req,a,trace)
    base=orig["packed"];cls=orig["singleton"];joint=orig["joint"]
    opt=dict(joint["pair_family"],compound=True)
    if getattr(a,"pool_study",False):
        source_pool=wide["joint"]["wave"]["settings"](req,a)["pool"]
        enhanced=dict(joint,pair_family=opt)
        return {"packed":base,"compound":enhanced,"reserved":dict(enhanced,spec_cells=source_pool["spec_cells"],sealed_redemption=1)}
    return {"packed":base,"singleton":cls,"wide":joint,"compound":dict(joint,pair_family=opt)}


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);out={}
    for case in a.cases:
        prog,plans,req=src.common.config(a,case)
        program=json.loads(prog.read_bytes())
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as base:
            gold=base({"audit":True})
        cfg=settings(req,a,True);arms={}
        with src.base.session(a.native,prog,plans) as infer:
            for name,params in cfg.items():
                v=infer(dict(params,audit=True,birth_ledger=True));assert "source_error" not in v,v.get("source_error")
                row=wide["analyze"](case,v,gold,program,{"singleton":"singleton","packed":"packed"}.get(name,"joint"))
                row["compound_work"]=v["multi"]["compound_work"]
                if name!="packed":
                    assert all(row[k]==arms["packed"][k] for k in wide["FIXED"]),(case,name)
                if name=="compound" and "wide" in arms:
                    assert row["expanded_multi"]==arms["wide"]["expanded_multi"]
                    assert row["family_counts"]["private_rows"]==arms["wide"]["family_counts"]["private_rows"]
                if name=="reserved":
                    st=row["staging"]=v["spec_cells"]["counts"];row["pool"]=v["spec_cells"]["pool"]
                    assert 0<st["used"]==st["payload_identity"] and st["used"]+st["unused"]==st["granted"]
                    assert st["slots_after_first_verify"]==0
                    assert row["denominators"]==arms["compound"]["denominators"]
                arms[name]=row;del v
                print(case,name,row["denominators"],row["per_packet"]["forward"],flush=True)
            cfg=settings(req,a,False)
            names=list(cfg)
            for lap in range(1+a.repeats):
                for name in names[lap%len(names):]+names[:lap%len(names)]:
                    v=infer(dict(cfg[name],audit=False))
                    assert v["state_sha"]==arms[name]["state_sha"] and v["runs"]==gold["runs"]
                    if lap:arms[name]["ms"].append(v["ms"])
            for row in arms.values():row["median_ms"]=median(row["ms"])
        out[case]=dict(runs=gold["runs"],arms=arms);(a.out/"results.json").write_text(json.dumps(out,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--pool-study",action="store_true")
    p.add_argument("--cases",nargs="+",default=["3mm","sum-bits"])
    p.add_argument("--repeats",type=int,default=4)
    a=p.parse_args();wide["joint"]["common"](a);main(a)
