"""Validate strict named-address releases and native source/physical parity."""
import argparse,json,importlib.util
from pathlib import Path
from statistics import median
from contextlib import ExitStack
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('strict_bake',HERE/'bake.py');bake=importlib.util.module_from_spec(sp);sp.loader.exec_module(bake);src=bake.src
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);res={};lib=json.loads(a.library.read_bytes())
    prov={"trust_index":getattr(a,"trust_index",None),"source_dir":getattr(a,"source_dir",None)}
    higher=getattr(a,"higher_cell",False)
    publication=getattr(a,"set_publication",False) or higher
    stored=getattr(a,"ripsat_library",None)
    if publication and stored is None and not getattr(a,"ripsat_evidence",None):
        raise ValueError(("--higher-cell" if higher else "--set-publication")+" requires --ripsat-library or --ripsat-evidence")
    if publication:
        prov["set_publication"]=True
    if higher:
        prov["higher_cell"]=True
        bake.ripsat["require_higher_capability"](a.native)
    if stored is not None and len(a.cases)!=1:
        raise ValueError("a precompiled RipSat library requires exactly one --cases target")
    if getattr(a,"donor",None) and not getattr(a,"ripsat_evidence",None):
        raise ValueError("--donor requires --ripsat-evidence")
    for case in a.cases:
        p,plan,req=src.config(a,case);ids,ix=bake.base['schema_map'](p)
        l1=lib['1']['paths'];l2=lib['2']['paths'];one=bake.relink(l1,ix);two=bake.relink(l2,ix)
        cfg={n:bake.settings(req,rule) for n,rule in {'leaf':{'depth':0},'compiled1':{'depth':1},'compiled2':{'depth':2},'baked1':{'depth':1,'library':one},'baked2':{'depth':2,'library':one+two}}.items()}
        if getattr(a,"ripsat_evidence",None) is not None:
            bridge=bake.ripsat
            artifact=bridge["build"](a.ripsat_evidence,bridge["donor_paths"](a.donor),p,**prov)
            bridge["write_artifact"](a.out/(case+"-ripsat-library.json"),artifact)
            cfg["ripsat"]=bake.settings(req,artifact["strict_named"])
        elif stored is not None:
            verified=bake.ripsat["load_checked"](stored,p,**prov)
            artifact=verified
            cfg["ripsat"]=bake.settings(req,artifact["strict_named"])
        if publication:
            cfg["ripsat"]=bake.settings(req,dict(artifact["strict_named"],partial=True))
            cfg["ripsat_set"]=bake.settings(req,artifact["set_publication_authorization"]["strict_named"])
            if higher:
                cfg["ripsat_higher"]=bake.settings(dict(req,source_sha256=artifact["target_sha256"]),
                                                   artifact["higher_cell_program"]["strict_named"])
        if getattr(a,"partial",False):
            cfg={key:dict(value,strict_named=dict(value["strict_named"],partial=True)) for key,value in cfg.items()}
        vd=a.exp/'compact-vanilla-20261121';arms={}
        with src.base.session(vd/'vanilla-audit',p)as get:gold=get(dict(audit=True))
        for n,req in cfg.items():
            with src.base.session(a.native,p,plan)as get:v=get(dict(req,audit=True,birth_ledger=True))
            assert 'source_error' not in v,(case,n,v.get('source_error'))
            if publication and n!='leaf':
                bake.ripsat["require_runtime_publication"](v)
            q=src.base.summarize(v,gold);del q['work'],q['rows']
            births=v['constructor_births'];owned={x[0]:x[4] for x in births['rows'] if x[3] and x[7]&1 and x[4]};end={x[0] for x in births['endpoint'] if x[2]==0}
            children=v['merge_child']['issued'];issued=sum(int(x['selected'])for x in children);packets=sum(q['emitted'])+issued
            q.update(stats=v['strict_named'],internal=v['integral_packets'],audit_score=v['single']['adaptive_rows']['decision_digest'],single_ledger=bake.base['digest'](v['single']['committed']),births=len(owned),visible=len(owned.keys()&end),birth_digest=bake.base['digest'](births['rows']),end_digest=bake.base['digest'](births['endpoint']),child_decisions=len(children),selected_children=issued,packets=packets,yield_per_packet=len(owned.keys()&end)/packets,ms=[])
            if getattr(a,"partial",False) and cfg[n]["strict_named"]["depth"]:
                if "partition" not in (v["strict_named"] or {}):
                    raise ValueError("--partial requires a strict-partial-named-ports native runtime")
            if n!='leaf':
                base=arms['leaf']
                for k in ('checks','commits','physical','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','rhs','state_sha','audit_score','single_ledger','child_decisions','selected_children','birth_digest','end_digest'):
                    assert q[k]==base[k],(case,n,k)
                stats=q['stats'] or {};c=stats.get('counts',{})
                assert c.get('released',0)==c.get('actual_internal',0)==c.get('source_commits',0)+stats.get('uncommitted',0)==base['emitted'][0]-q['emitted'][0]
                q['by_depth']=[[sum(cnt[i] for path,cnt in q['stats']['routes'] if len(path)==depth) for i in range(3)]for depth in (1,2)]
                assert q['by_depth'][1][2]==c['two_with_internal_parent']
            if n=="ripsat_set":
                counters=bake.ripsat["require_runtime_publication"](v)
                if (counters["confirmed"]!=q["by_depth"][1][2] or
                    counters["active_middles"]!=q["by_depth"][0][2] or
                    counters["encoded"]!=q["stats"]["counts"]["tagged"]):
                    raise ValueError("Set publication report disagrees with the authenticated second hop")
            if n=="ripsat_higher":
                work=bake.ripsat["require_runtime_higher"](v)
                if work["terminal_commits"]!=q["by_depth"][1][2]:
                    raise ValueError("higher Cell terminal count disagrees with the signed original-Run releases")
                q["higher_work"]=work
            arms[n]=q
            print(case,n,q['emitted'],q.get('by_depth'),q['yield_per_packet'],flush=True)
            del v
        n='compiled2'
        with src.base.session(a.native,p,plan)as get:v=get(dict(cfg[n],strict_named=dict(cfg[n]['strict_named'],wrong_port=True)))
        fault={'error':v.get('source_error'),'runs':v['runs']}
        if arms[n]['stats']['counts']['released']:assert 'strict named return port corruption' in fault['error']
        with src.base.session(a.native,p,plan)as get:
            names=list(arms)
            for lap in range(1+a.repeats):
                seq=names[lap%len(names):]+names[:lap%len(names)]
                for n in seq if lap%2 else reversed(seq):
                    v=get(cfg[n]);assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['root_recipe']['emitted']==arms[n]['emitted']
                    if n=="ripsat_set" and bake.ripsat["require_runtime_publication"](v)!=arms[n]["stats"]["set_publication"]:
                        raise ValueError("production Set publication differs from the audited program")
                    if n=="ripsat_higher" and bake.ripsat["require_runtime_higher"](v)!=arms[n]["higher_work"]:
                        raise ValueError("production higher Cell requests or branches differ from the audited run")
                    if n!='leaf':arms[n]['production']=(v['strict_named'] or {}).get('counts',{});assert arms[n]['production'].get('source_commits',0)==(arms[n]['stats'] or {}).get('counts',{}).get('source_commits',0)
                    if lap:arms[n]['ms'].append(v['ms'])
        for q in arms.values():q['median_ms']=median(q['ms'])
        res[case]=dict(arms=arms,fault=fault,relinked=[len(one),len(two)],runs=gold['runs'],rhs=gold['rhs_count']);(a.out/'results.json').write_text(json.dumps(res,separators=(',',':'))+'\n')
        print(case,[(k,round(q['median_ms'],2))for k,q in arms.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','library','out'):p.add_argument(k,type=Path)
    bake.ripsat["add_study_args"](p)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=3);run(p.parse_args())
