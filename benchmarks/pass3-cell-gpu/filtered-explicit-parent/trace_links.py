"""Credit each final constructor origin once to its actual signed template instance."""
from collections import Counter
from pathlib import Path
from runpy import run_path
import argparse
import json

HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/"complete_library.py"))
driver=study["driver"]; strict=study["strict"]


def capture(v,base):
    receipt=v["strict_named"]
    links=receipt["links"]
    by_serial={c:(r,d) for c,r,d in links}
    commits={r[2]:r for r in v["root_recipe"]["commits"]}
    assert len(by_serial)==len(links)==receipt["counts"]["source_commits"]
    for child,(root,depth) in by_serial.items():
        assert root in commits and root not in by_serial and commits[child][5]>commits[root][5]
        assert depth in (1,2)
    retained={f for f,_,hidden in v["constructor_births"]["endpoint"] if not hidden}
    extras={c["allocated"]<<32 for c in v["merge_child"]["issued"] if c["allocated"] is not None}
    groups={r:Counter() for _,r,_ in links}
    births=Counter();sources=Counter()
    for fid,table,epoch,ctor,serial,_,_,flags in v["constructor_births"]["rows"]:
        if not (ctor and serial and flags&1):continue
        final=fid in retained
        births['owned']+=1;births['visible']+=int(final)
        if serial in by_serial:
            root,depth=by_serial[serial];kind='internal'
        elif serial in groups:
            root=serial;kind='producer'
        else:continue
        separate=fid in extras
        source='paid_merge_child' if separate else 'runtime_dynamic' if flags&2 else 'typed'
        sources[kind,source,'births']+=1;sources[kind,source,'visible']+=int(final)
        if not separate:
            groups[root][kind+'_births']+=1;groups[root][kind+'_visible']+=int(final)
    assert births['visible']==base['visible'] and births['owned']==base['births']
    totals=Counter(g['producer_visible']+g['internal_visible'] for g in groups.values())
    child_yield=Counter(g['internal_visible'] for g in groups.values())
    assert sum(totals.values())==len(groups)
    return dict(credited_external_roots=len(groups),internal_source_commits=len(links),
                typed_and_dynamic_sources={".".join(k):n for k,n in sorted(sources.items())},
                endpoint_yield_hist=sorted(totals.items()),increment_from_internal=sorted(child_yield.items()),
                actual_internal_visible_excluding_paid_child=sum(i*n for i,n in child_yield.items()),
                visible=births['visible'],births=births['owned'],link_depth=dict(Counter(d for _,_,d in links)))


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    lib=json.loads(a.library.read_bytes());reference=json.loads(a.reference.read_bytes())
    data={}
    for case in ("sum-bits","3mm"):
        pp,plans,req=strict.src.config(a,case)
        _,idx=strict.bake.base["schema_map"](pp)
        one=study["extend"](pp,idx,lib["1"]["consumers"])
        options={"compiled1":{"depth":1},"compiled2":{"depth":2},
                 "complete1":{"depth":1,"library":[[x] for x in one]}}
        rows={}
        with strict.src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",pp) as run_ref:
            gold=run_ref({"audit":True})
        for name,opt in options.items():
            cfg=driver["filtered"](req,dict(opt,record_links=True))
            with strict.src.base.session(a.native,pp,plans) as infer:v=infer(dict(cfg,audit=True,birth_ledger=True))
            assert 'source_error' not in v,v.get('source_error')
            q=strict.src.base.summarize(v,gold);base=reference[case]['arms']['leaf']
            assert q['aligned'] and all(q['checks'].values())
            assert all(q[k]==base[k] for k in ("physical","root_ids","nested_ids","children","state_sha","commits","root_parents"))
            rows[name]=capture(v,base)
            print(case,name,rows[name]['actual_internal_visible_excluding_paid_child'],rows[name]['internal_source_commits'],flush=True)
        data[case]=rows
        (a.out/"links.json").write_text(json.dumps(data,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","library","reference","out"):p.add_argument(k,type=Path)
    run(p.parse_args())
