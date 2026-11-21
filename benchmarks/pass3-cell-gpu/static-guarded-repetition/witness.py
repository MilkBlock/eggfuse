"""Recover one fully committed chain and count benefits across all (even failed) paid tokens."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"study.py"))


def witness(raw,program):
    rows=raw["strict_named"]["signed_commits"]
    times={r[2]:r for r in raw["root_recipe"]["commits"]}
    endpoints={f for f,t,h in raw["constructor_births"]["endpoint"] if not h}
    paid={r["allocated"]<<32 for r in raw["merge_child"]["issued"] if r["allocated"] is not None}
    child_origin={s:root for s,root,*_ in rows}
    facts=defaultdict(list);creation={}
    for f,t,epoch,ctor,s,ancestor,cross,flags in raw["constructor_births"]["rows"]:
        if not ctor or not s or not(flags&1) or flags&2 or f in paid:continue
        creation[f]=s
        if f in endpoints:facts[s].append((f,t))
    tables=[t["name"] for t in program["recipe"]["tables"]]
    chain_index={}
    for ser,root,path,ports,run in rows:
        key=(root,tuple(map(tuple,ports)),tuple(map(tuple,path)),run)
        assert key not in chain_index
        chain_index[key]=ser
    depth=max(len(path) for _,_,path,_,_ in rows)
    longest=[]
    for s,root,path,ports,run in rows:
        if len(path)!=depth:continue
        steps=[]
        for i,(edge,coords) in enumerate(zip(path,ports)):
            pr,op,rid=edge;cell,pos,version,producer_run=coords
            at=ports[i+1][3] if i+1<depth else run
            child=chain_index[(root,tuple(map(tuple,ports[:i+1])),tuple(map(tuple,path[:i+1])),at)]
            parent=root if i==0 else steps[-1]["child_serial"]
            assert times[parent][3]==pr and times[child][3]==rid and times[parent][5]==producer_run<at
            assert pos==op and creation[cell<<32|op]==parent
            steps.append(dict(producer=parent,child_serial=child,from_rule=pr,to_rule=rid,op=op,
                              actual_ref=[cell,pos],version=version,run=at,typed_visible=list(facts[child])))
        n=sum(len(st["typed_visible"]) for st in steps)
        longest.append((n,root,s,steps))
    n,root,s,steps=max(longest,key=lambda x:(x[0],-x[1],-x[2]))
    root_rec=times[root]
    for st in steps:st["typed_visible"]=[[f,tables[t]] for f,t in st["typed_visible"]]
    extra=Counter()
    for s,r in child_origin.items():extra[r]+=len(facts[s])
    paid_tokens=sum(raw["root_recipe"]["emitted"])+raw["merge_child"]["counts"][1]
    hist=Counter(extra.values());hist[0]+=paid_tokens-len(extra)
    assert sum(k*v for k,v in hist.items())==sum(len(facts[s]) for s in child_origin)
    return dict(issued_tokens=paid_tokens,depth=depth,deepest_terminal_commits=len(longest),
                internal_typed_increment_hist=sorted(hist.items()),root_rule=root_rec[3],
                root_serial=root,root_Run=root_rec[5],named_parents=root_rec[6],producer_typed_visible=len(facts[root]),
                typed_visible_on_this_chain=n,steps=steps)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("exp","native","out"):p.add_argument(n,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);result={}
    for c in ("sum-bits","3mm"):
        prog,plans,req=study["src"].config(a,c)
        cfg=study["guard"]["base"]["filtered"](req,dict(depth=8,partial=True,value_guards=True,repeat=True,record_links=True))
        with study["src"].base.session(a.native,prog,plans) as infer:raw=infer(dict(cfg,birth_ledger=True,audit=True))
        assert "source_error" not in raw
        result[c]=witness(raw,json.loads(prog.read_bytes()))
        print(c,result[c]["depth"],result[c]["typed_visible_on_this_chain"],result[c]["internal_typed_increment_hist"][-5:],flush=True)
        (a.out/"witnesses.json").write_text(json.dumps(result,indent=2)+"\n")
