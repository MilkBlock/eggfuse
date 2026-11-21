"""Execute held-out static template libraries chosen by donor packet or terminal-node return."""
import argparse
import json
from pathlib import Path
from native import strict,shared,driver,summarize

def selection(targets,p,idx,guards):
    # Freeze consumer schemas on donors; link only concrete statically typed op sites.
    if not guards:
        return sorted(shared["extend"](p,idx,targets))
    rules=json.loads(p.read_bytes())["recipe"]["rules"]
    consumers={}
    for schema in targets:
        rid=idx.get(schema)
        if rid is None:continue
        query=rules[rid]["query"]
        assert "table" in query[0]["call"] and all("primitive" in atom["call"] for atom in query[1:])
        consumers.setdefault(query[0]["call"]["table"], []).append(rid)
    return sorted([producer,op,child] for producer,r in enumerate(rules)
                  for op,e in enumerate(r["effects"]) if e.get("kind")=="construct"
                  for child in consumers.get(e.get("call",{}).get("table"),()))


def study(a):
    a.out.mkdir(parents=True,exist_ok=False)
    policy=json.loads(a.policy.read_bytes());ranked=policy["ranked"];partial=policy.get("partial",False)
    result={}
    for case in a.cases:
        p,plan,req=strict.src.config(a,case)
        schemas,idx=strict.bake.base["schema_map"](p)
        with strict.src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",p) as get:gold=get({"audit":True})
        arms={"leaf":{"depth":0},"all":{"depth":1}}
        for objective in ("commits","typed","typed_and_dynamic"):
            for k in (1,2):
                targets=[r[0] for r in ranked[objective][:k]]
                arms[f"{objective}-{k}"]={"depth":1,"library":[[e] for e in selection(targets,p,idx,policy.get("value_guards",False))]}
        same={}
        group={}
        for name,opt in arms.items():
            key=json.dumps(opt,sort_keys=True)
            if key in same:
                group[name]=dict(group[same[key]],identical_config=same[key])
                continue
            opt["record_links"]=True;opt["partial"]=partial;opt["value_guards"]=policy.get("value_guards",False)
            cfg=driver["filtered"](req,opt)
            with strict.src.base.session(a.native,p,plan) as get:
                v=get(dict(cfg,audit=True,birth_ledger=True))
                rec=summarize(v,gold,schemas)
                stats=v["strict_named"] or {}; del v
                # Check that the timed/production path carries the same external decisions and
                # never uses the audit's independent child matching or score oracle.
                prod=get(dict(cfg,audit=False))
                assert prod["state_sha"]==rec["source"] and prod["runs"]==rec["runs"]
                counts=(prod["strict_named"] or {}).get("counts",{})
                assert counts.get("source_commits",0)==rec["removed"]
                if not partial:assert counts.get("no_score_inputs",0)==rec["removed"]
                assert counts.get("audit_score_inputs",0)==0
                q=prod["root_recipe"]["emitted"]
                assert sum(q)+prod["merge_child"]["counts"][1]==rec["packets"]
                rec.update(programs=len(opt.get("library",[])) if "library" in opt else None,availability=stats.get("availability",{}))
            if name!="leaf":
                base=group["leaf"]
                for k in ("source","rhs","runs","visible","born","origin_sha","parents","physical","writes","children","child_packets"):
                    assert rec[k]==base[k],(case,name,k)
                assert rec["packets"]+rec["removed"]==base["packets"]
            group[name]=rec;same[key]=name
            print(case,name,rec["programs"],rec["removed"],rec["typed"],rec["fept"],flush=True)
        result[case]=group
        (a.out/"results.json").write_text(json.dumps(result,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","policy","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    study(p.parse_args())
