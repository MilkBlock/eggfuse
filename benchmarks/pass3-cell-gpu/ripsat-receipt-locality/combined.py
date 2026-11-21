"""Cross private higher-Cell specialization with version-indexed validation of known ports."""
import argparse,json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/"ripsat-higher-cell/study.py"))
mat=run_path(str(HERE.parent/"ripsat-publication-matrix/study.py"))
src=base["source"]
ARMS=(("direct",False,0),("direct-index",False,2),("higher",True,0),("higher-index",True,2))


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        p,plans,req=src.config(a,case)
        donors={n:a.exp/"compact-holdouts-20261121-v1"/(n+"-1703")/"program.json" for n in ("dot-product","jacobi-1d")}
        cert=mat["authorizer"]["load_checked"](mat["AUTH"]/(case+".json"),HERE.parent/"ripsat-donor-evidence/evidence.json",donors,p)
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",p) as get:gold=get({"audit":True})
        def params(name,higher,index,*,audit=False,profile=False):
            cfg=base["settings"](req,cert,"higher" if higher else "direct",audit=audit,profile=profile)
            cfg["strict_named"].update(receipt_scan=index,receipt_profile=profile)
            return cfg
        arms={}
        ordinals={}
        for arm in ARMS:
            name,higher,index=arm
            with src.base.session(a.native,p,plans) as get:
                v=get(params(*arm,audit=True))
            q,ords=mat["summarize"](v,gold,True);sig=v["strict_named"]
            q["owners"]=sig["higher_cell"]["counts"];q["scan"]=sig["receipt_scan"]
            q["profiles"]=[];q["ms"]=[]
            if name!="direct":
                for k in (*mat["FIXED"],"emitted","packets","internal","set_internal","signed_ordinals_sha","terminal_ordinals_sha"):
                    assert q[k]==arms["direct"][k],(case,name,k)
                assert ords==ordinals["direct"]
            if higher:
                assert sig["higher_cell"]["enabled"] and q["owners"]["terminal_commits"]==q["set_internal"]>0
                assert q["owners"]["transferred"]>=q["set_internal"]
            ordinals[name]=ords;arms[name]=q
        with src.base.session(a.native,p,plans) as get:
            for lap in range(a.repeats+1):
                order=ARMS[lap%4:]+ARMS[:lap%4]
                for arm in order if lap%2 else reversed(order):
                    q=arms[arm[0]];v=get(params(*arm))
                    assert v["runs"]==q["runs"] and v["state_sha"]==q["state_sha"] and v["root_recipe"]["emitted"]==q["emitted"]
                    if lap:q["ms"].append(v["ms"])
            for lap in range(4):
                for arm in ARMS[lap:]+ARMS[:lap]:
                    v=get(params(*arm,profile=True))
                    assert v["state_sha"]==gold["state_sha"]
                    sig=v["strict_named"]
                    if lap:arms[arm[0]]["profiles"].append(dict(scan=sig["receipt_scan"],owners=sig["higher_cell"]["counts"]))
        for q in arms.values():q["median_ms"]=median(q["ms"])
        data[case]=arms;(a.out/"joint.json").write_text(json.dumps(data,indent=1)+"\n")
        print(case,[(n,q["packets"],q["scan"]["row_reads"],round(q["median_ms"],2),round(median(p["scan"]["receiver_ns"]+p["scan"]["index_ns"] for p in q["profiles"])/1e6,3)) for n,q in arms.items()],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    p.add_argument("--repeats",type=int,default=4)
    run(p.parse_args())
