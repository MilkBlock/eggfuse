"""Attribute terminal typed nodes to actually accepted static child invocations."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
shared=run_path(str(HERE.parent/"filtered-explicit-parent/complete_library.py"))
driver=shared["driver"]
strict=shared["strict"]


def digest(data):
    return hashlib.sha256(json.dumps(data,separators=(",", ":")).encode()).hexdigest()


def summarize(v,gold,schemas):
    assert "source_error" not in v, v.get("source_error")
    q=strict.src.base.summarize(v,gold)
    assert q["aligned"] and all(q["checks"].values())
    info=v["strict_named"] or {}
    records=v["constructor_births"]
    endpoints={f for f,_,hidden in records["endpoint"] if not hidden}
    commits={r[2]: r for r in v["root_recipe"]["commits"]}
    links={c:(r,d) for c,r,d in info.get("links",[])}
    paid={child["allocated"]<<32 for child in v["merge_child"]["issued"] if child["allocated"] is not None}
    assert len(links)==info.get("counts",{}).get("source_commits",0)
    outcome={}
    def bucket(schema):
        return outcome.setdefault(schema,Counter())
    for c,(r,d) in links.items():
        assert r in commits and r not in links and commits[c][5]>commits[r][5]
        assert d in (1,2)
        bucket(schemas[commits[c][3]])["commits"]+=1
    direct_visible=set()
    fresh=0
    for f,_,_,constructor,c,_,_,flags in records["rows"]:
        if not (constructor and c and flags&1):
            continue
        assert c in commits
        fresh+=1
        if f not in endpoints:
            continue
        direct_visible.add(f)
        if c in links:
            origin="independent_child" if f in paid else "dynamic" if flags&2 else "typed"
            bucket(schemas[commits[c][3]])[origin]+=1
    decisions=v["root_recipe"]["emitted"]
    nested=v["merge_child"]["counts"][1]
    packets=sum(decisions)+nested
    return dict(outcome=outcome,visible=len(direct_visible),born=fresh,packets=packets,
                child_packets=nested,source=q["state_sha"],rhs=q["rhs"],runs=v["runs"],checks=q["checks"],
                origin_sha=digest(sorted(direct_visible)),parents=q["root_parents"],
                physical=q["physical"],writes=q["commits"],children=q["children"],
                removed=len(links),typed=sum(x["typed"] for x in outcome.values()),
                dynamic=sum(x["dynamic"] for x in outcome.values()),paid=sum(x["independent_child"] for x in outcome.values()),
                registered=info.get("counts",{}).get("named_ports",0),
                fept=len(direct_visible)/packets)
