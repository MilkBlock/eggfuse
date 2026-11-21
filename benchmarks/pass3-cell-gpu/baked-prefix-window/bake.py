"""Train prefix-window admission on observed high-arity subtree sizes; projection only."""
import json
from collections import defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
DONORS=("dot-product","jacobi-1d")
TEST=("conjugate-gradient","3mm")


def samples(case,width):
    return json.loads((HERE/"hist"/f"{case}-{width}.json").read_bytes())


def shapes(x):
    _,degree,width,fresh,root,second,last,suffix=x
    age=0 if not fresh else 1 if fresh<width else 2
    # Ordered from specific to broad. The library shares by query shape rather than rule ID.
    return [(degree,age,root//2,second//2,last//2,suffix),(degree,age,second//2,suffix),(degree,age),()]


def run():
    result={}
    for width in (16,64):
        table=defaultdict(lambda:[0,0])
        for case in DONORS:
            for features,y,count in samples(case,width)["windows"]:
                for key in shapes(features):
                    table[key][0]+=count
                    table[key][1]+=count*(y-1)
        for case in TEST:
            stats=samples(case,width)
            policies={k:[0,0] for k in ("all","donor","oracle")}
            paying=nonempty=total=0
            for x,y,freq in stats["windows"]:
                key=next(k for k in shapes(x) if k in table and table[k][0]>=8)
                nonempty+=freq*int(y>0);paying+=freq*int(y>1);total+=freq
                for k,select in (("all",True),("donor",table[key][1]>0),("oracle",y>1)):
                    if select:
                        policies[k][0]+=freq;policies[k][1]+=(y-1)*freq
            result[f"{case}/{width}"]=dict(windows=total,paying=paying,nonempty=nonempty,high_arity_packets=stats["captured"],
                measured_forward=stats["packets"],visible=stats["visible"],estimates={k:dict(actions=n,saved=save,
                    projected_forward=stats["packets"]-save,projected_fept=stats["visible"]/(stats["packets"]-save))
                    for k,(n,save) in policies.items()})
    return result


if __name__=="__main__":
    (HERE/"bounds.json").write_text(json.dumps(run(),indent=2)+"\n")
