"""Capture all eligible signed offers, including unselected candidates, from complete donor runs."""
import argparse,json
from pathlib import Path
from driver import source,request
DONORS=("sum-bits","dot-product","jacobi-1d")

def capture(a):
    a.out.mkdir(parents=True,exist_ok=False)
    for case in a.cases:
        p,plans,req=source.common.config(a,case)
        with source.base.session(a.exp/"compact-vanilla-20261121/vanilla",p) as oracle:gold=oracle({})
        with source.base.session(a.native,p,plans) as infer:v=infer(request(req,"capture",True))
        assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"] and v["multi"]["total_rhs"]==gold["rhs_count"]
        report=v["spec_cells"]["lane_rank"];groups=report["groups"];stats=report["counts"]
        assert groups and sum(no+yes for _,_,_,rows in groups for _,no,yes in rows)==stats["lanes"]
        assert all(len(x)==12 and all(0<=i<=8 for i in x) for _,_,_,rows in groups for x,_,_ in rows)
        (a.out/(case+".json")).write_text(json.dumps(dict(case=case,graph=v["state_sha"],rhs=gold["rhs_count"],counts=stats,groups=groups,hist=report["hist"]),separators=(",",":"))+"\n")
        print(case,len(groups),stats["lanes"],sum(yes for _,_,_,rows in groups for _,_,yes in rows),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=DONORS);p.add_argument("--seed",type=int,default=1703);capture(p.parse_args())
