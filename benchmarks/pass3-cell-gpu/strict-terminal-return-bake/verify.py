"""Independently reconstruct donor rankings and check the actual held-out receipts."""
import json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent

def load(name):
    return json.loads((HERE/name).read_bytes())


def verify():
    for mode in ("whole","partial","guards"):
        p=load(mode+"-policy.json");data=load(mode+".json")
        if mode=="whole":data.update(load("transfer.json"))
        assert set(p["donors"])=={"dot-product","jacobi-1d"} and set(p["donors"]).isdisjoint(data)
        totals=Counter()
        for v in p["donors"].values():
            assert all(v["checks"].values())
            for s,d in v["outcome"].items():
                for k,n in d.items():totals[s,k]+=n
        for k,ranking in p["ranked"].items():
            def score(s):
                return totals[s,"typed"]+totals[s,"dynamic"] if k=="typed_and_dynamic" else totals[s,k]
            candidates=sorted({s for s,_ in totals if score(s)>0},key=lambda s:(-score(s),s))
            assert ranking==[[s,score(s)] for s in candidates]
        for c,arms in data.items():
            ref=arms["leaf"]
            for name,v in arms.items():
                assert all(v["checks"].values())
                for k in ("source","rhs","runs","visible","born","origin_sha","parents","physical","writes","children","child_packets"):
                    assert v[k]==ref[k],(c,name,k)
                assert v["packets"]==ref["packets"]-v["removed"]
                assert v["fept"]==v["visible"]/v["packets"]
                assert v["typed"]==sum(x.get("typed",0) for x in v["outcome"].values())
                assert v["removed"]==sum(x.get("commits",0) for x in v["outcome"].values())
                if name not in ("all","leaf"):
                    objective,budget=name.rsplit("-",1)
                    assert set(v["outcome"]).issubset({s for s,_ in p["ranked"][objective][:int(budget)]})
    print("Verified frozen donor objectives and actual strict source releases on four held-out programs.")


if __name__=="__main__":
    verify()
