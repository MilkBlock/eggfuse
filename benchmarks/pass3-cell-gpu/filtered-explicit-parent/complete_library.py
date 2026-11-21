"""Precompile every typed producer port into the donor-selected consumer schemas.

This ablation tests whether requiring the exact observed producer schema in the
donor is what prevents a signed child table from being complete on transfer.
All candidate edges are frozen from the compiled program before the Run.
"""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/"study.py"))
strict=driver["strict"]


def extend(program,idx,targets):
    rules=json.loads(program.read_bytes())["recipe"]["rules"]
    table_map={}
    for name in targets:
        rid=idx.get(name)
        if rid is None:
            continue
        r=rules[rid]
        assert len(r["query"])==1
        a=r["query"][0]
        assert "table" in a["call"] and all("slot" in x for x in a["args"])
        table_map.setdefault(a["call"]["table"],[]).append(rid)
    edges=[]
    for producer,r in enumerate(rules):
        for op,ins in enumerate(r["effects"]):
            if ins.get("kind")!="construct":
                continue
            for child in table_map.get(ins.get("call",{}).get("table"),[]):
                edges.append([producer,op,child])
    return edges


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    library=json.loads(a.library.read_bytes());results={}
    for case in a.cases:
        pp,plans,request=strict.src.config(a,case)
        _,index=strict.bake.base["schema_map"](pp)
        first=extend(pp,index,library["1"]["consumers"])
        second=extend(pp,index,library["2"]["consumers"])
        base=[[edge] for edge in first]
        chained=[[x,y] for x in first for y in second if x[-1]==y[0]]
        options={"complete1":{"depth":1,"library":base},"complete2":{"depth":2,"library":base+chained}}
        ref=json.loads(a.reference.read_bytes())[case]["arms"]["leaf"]
        with strict.src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",pp) as oracle:gold=oracle({"audit":True})
        rows={}
        for name,opt in options.items():
            req=driver["filtered"](request,opt)
            with strict.src.base.session(a.native,pp,plans) as infer:
                v=infer(dict(req,audit=True,birth_ledger=True))
                assert "source_error" not in v,v.get("source_error")
                q=strict.src.base.summarize(v,gold)
                assert q["aligned"] and all(q["checks"].values())
                for field in ("physical","root_ids","nested_ids","children","state_sha","commits","root_parents"):
                    assert q[field]==ref[field],(case,name,field)
                b=v["constructor_births"]
                born={x[0] for x in b["rows"] if x[3] and x[4] and x[7]&1}
                visible={x[0] for x in b["endpoint"] if not x[2]} & born
                assert len(visible)==ref["visible"]
                emitted=v["root_recipe"]["emitted"];child=v["merge_child"]["counts"][1]
                packets=sum(emitted)+child
                production=infer(req)
                assert production["state_sha"]==v["state_sha"] and production["root_recipe"]["emitted"]==emitted
                counts=production["strict_named"]["counts"]
                assert ref["packets"]-packets==counts["source_commits"]==counts["no_score_inputs"]
                rows[name]=dict(paths=len(opt["library"]),eligible_consumers=sorted({path[-1][-1] for path in opt["library"]}),
                                packets=packets,visible=len(visible),fept=len(visible)/packets,checks=q["checks"],
                                state_sha=v["state_sha"],counts=counts)
                print(case,name,len(opt["library"]),counts["source_commits"],flush=True)
        results[case]=rows
        (a.out/"results.json").write_text(json.dumps(results,indent=1)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","library","reference","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    run(p.parse_args())
