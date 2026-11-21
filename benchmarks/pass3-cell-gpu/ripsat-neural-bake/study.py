"""Compare leaf, committed-trace and real RipSat templates on the same neural parents."""
import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE=Path(__file__).resolve().parent
named=run_path(str(HERE.parent/"explicit-parent-cell-composition/study.py"))
bake=named["bake"]
src=named["src"]
partial=run_path(str(HERE.parent/"strict-guarded-return/study.py"))
summarize=partial["analyze"]
IDENTITY=("rhs","runs","source","physical","parents","ids","nested","commits","children","scores","born","visible","child")


def candidates(trace,program):
    _,idx=bake.base["schema_map"](program)
    first=bake.relink(trace["1"]["paths"],idx)
    second=bake.relink(trace["2"]["paths"],idx)
    return {"depth":2,"library":first+second}


def options(legacy,rip):
    def keys(v):return {tuple(map(tuple,path)) for path in v["library"]}
    a,b=keys(legacy),keys(rip)
    union=sorted(a|b)
    return {"leaf":{"depth":0},"trace":legacy,"ripsat":rip,
            "union":{"depth":max(legacy["depth"],rip["depth"]),"library":[list(map(list,path)) for path in union]}},dict(
                trace=len(a),ripsat=len(b),shared=len(a&b),ripsat_only=len(b-a),trace_only=len(a-b))


def execute(a):
    a.out.mkdir(parents=True,exist_ok=False)
    bridge=bake.ripsat
    donors=bridge["donor_paths"](a.donor)
    trace=json.loads(a.trace_library.read_bytes())
    data={}
    for case in a.cases:
        program,plans,req=src.config(a,case)
        # Compile independently for this exact target. No trace-derived routes
        # are passed into the RipSat compiler.
        artifact=bridge["build"](a.evidence,donors,program)
        bridge["write_artifact"](a.out/(case+"-ripsat.json"),artifact)
        specs,counts=options(candidates(trace,program),artifact["strict_named"])
        if "strict_named_static_consumer" in artifact:
            specs["local_return"]=artifact["strict_named_static_consumer"]
        settings={}
        for name,spec in specs.items():
            config=bake.settings(req,dict(spec,partial=True))
            settings[name]=dict(config,rows=dict(config["rows"],scalar_certificates=True),
                                integral_root="off",integral_packets=False)
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",program) as oracle:
            gold=oracle({"audit":True})
        arms={}
        for name,cfg in settings.items():
            with src.base.session(a.native,program,plans) as run:
                v=run(dict(cfg,audit=True,birth_ledger=True,strict_named=dict(cfg["strict_named"],record_links=True)))
            q=summarize(v,gold)
            stats=v["strict_named"] or {}
            # Immutable source ordinals permit comparing the actual set of paid
            # choices even when multiple potential producers satisfy one child.
            ord_by_serial={r[2]:r[0] for r in v["root_recipe"]["commits"]}
            paths={};active=set()
            child_path={};examples={}

            legal={tuple(map(tuple,path)) for path in specs[name].get("library",[])}
            for child,root,path,ports,run_no in stats.get("signed_commits",[]):
                assert len(path)==len(ports)
                edge=tuple(map(tuple,path));assert edge in legal
                label=json.dumps(path,separators=(",",":"))
                paths[label]=paths.get(label,0)+1
                child_path[child]=label
                if label not in examples:
                    root_commit=v["root_recipe"]["commits"][ord_by_serial[root]-1]
                    assert root_commit[2]==root
                    examples[label]=dict(root_rule=root_commit[3],root_run=root_commit[5],named_parents=root_commit[6],
                                         applied_path=path,returned_ports=ports,child_run=run_no,child_ordinal=ord_by_serial[child])

                assert ord_by_serial[root]<ord_by_serial[child] and ord_by_serial[child] not in active
                active.add(ord_by_serial[child])
            origins=v["constructor_births"]
            visible={f for f,_,hidden in origins["endpoint"] if not hidden}
            paid={child["allocated"]<<32 for child in v["merge_child"]["issued"] if child["allocated"] is not None}
            contribution={path:{"typed":[0,0],"dynamic":[0,0],"paid":[0,0]} for path in paths}
            for f,t,epoch,ctor,serial,_,_,flags in origins["rows"]:
                if serial not in child_path or not ctor or not flags&1:continue
                kind="paid" if f in paid else "dynamic" if flags&2 else "typed"
                totals=contribution[child_path[serial]][kind]
                totals[0]+=1;totals[1]+=int(f in visible)
            q.update(active_paths=paths,path_nodes=contribution,examples=examples,covered_ordinals=sorted(active),programs=len(legal))

            assert q["internal"]==len(active)
            if name!="leaf":
                assert all(q[k]==arms["leaf"][k] for k in IDENTITY),(case,name)
                assert arms["leaf"]["packets"]-q["packets"]==q["internal"]
            arms[name]=q;del v
            print(case,name,len(legal),q["internal"],q["fept"],flush=True)
        with src.base.session(a.native,program,plans) as run:
            names=list(arms)
            for lap in range(a.repeats+1):
                for name in names[lap%len(names):]+names[:lap%len(names)]:
                    v=run(settings[name]);q=arms[name]
                    assert "source_error" not in v,v.get("source_error")
                    assert v["state_sha"]==gold["state_sha"] and v["runs"]==gold["runs"] and v["root_recipe"]["emitted"]==q["emitted"]
                    if name!="leaf":
                        production=(v["strict_named"] or {}).get("counts",{})
                        assert production.get("source_commits",0)==q["internal"] and production.get("audit_score_inputs",0)==0
                        q["production"]=production
                    if lap:q["ms"].append(v["ms"])
        for v in arms.values():v["median_ms"]=median(v["ms"])
        data[case]={"library":counts,"arms":arms}
        (a.out/"results.json").write_text(json.dumps(data,separators=(",",":"))+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","evidence","trace_library","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--donor",action="append",required=True,metavar="NAME=PROGRAM.json")
    p.add_argument("--cases",nargs="+",default=["dot-product","sum-bits","3mm"])
    p.add_argument("--repeats",type=int,default=3)
    execute(p.parse_args())
