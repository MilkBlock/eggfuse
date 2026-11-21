import json
from pathlib import Path
from math import isclose
HERE=Path(__file__).resolve().parent
def load(n):return json.loads((HERE/n).read_bytes())
data=load("results.json");rss=load("rss.json");trails=load("witnesses.json")
for case,arms in data.items():
    leaf=arms["0"]
    for limit,q in arms.items():
        assert q["packets"]==leaf["packets"]-q["internal"] and isclose(q["fept"],q["visible"]/q["packets"])
        assert sum(q["depths"].values())==q["internal"]
        assert all(int(d)<=int(limit) for d in q["depths"])
        assert all(q[k]==leaf[k] for k in ("rhs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child"))
        assert all(q["checks"].values())
        for s in rss[case]["arms"][limit]:
            tr=s["trace"];abs_kib,delta_kib=rss[case]["limits_kib"]
            for k,level in (("absolute",abs_kib),("increment",tr[0][1]+delta_kib)):
                t=next((x for x,b in tr if b>=level),None)
                assert s["crossings"][k]==["unreached" if t is None else "left" if tr[0][1]>=level else "reached",t]
    w=trails[case];assert len(w["steps"])==w["depth"] and w["named_parents"]
    assert sum(n for _,n in w["internal_typed_increment_hist"])==arms['8']['packets']
    assert sum(k*n for k,n in w["internal_typed_increment_hist"])==sum(arms['8']['typed_visible_by_depth'].values())
    assert len({f for st in w["steps"] for f,t in st["typed_visible"]})==w["typed_visible_on_this_chain"]
    for i,st in enumerate(w["steps"]):
        assert st["actual_ref"][1]==st["op"]
        assert st["producer"]==(w["root_serial"] if i==0 else w["steps"][i-1]["child_serial"])
print("Verified bounded signed recurrence, source identities, per-depth typed origins, exact chain and fixed RSS crossings.")
