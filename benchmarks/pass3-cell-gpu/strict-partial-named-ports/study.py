"""Run strict disjoint partial ownership and classify actual original endpoint births."""
import argparse,hashlib,json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
complete=run_path(str(HERE.parent/'filtered-explicit-parent/complete_library.py'))
driver=complete['driver'];strict=complete['strict'];src=strict.src
digest=strict.bake.base['digest']
MODES=('leaf','whole','partial','partial2','donor_whole','donor_partial')
KEYS=('checks','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','rhs','state_sha','commits','physical','all_single','audit_score','birth_digest','endpoint_digest','births','visible','paid_choices','paid_tokens','global_kinds')
def options(p):
    lib=json.loads((HERE.parent/'explicit-parent-cell-composition/library.json').read_bytes());_,ix=strict.bake.base['schema_map'](p)
    edges=complete['extend'](p,ix,lib['1']['consumers']);chosen=[[x] for x in edges]
    return dict(leaf=dict(depth=0),whole=dict(depth=1),partial=dict(depth=1,partial=True),partial2=dict(depth=2,partial=True),
                donor_whole=dict(depth=1,library=chosen),donor_partial=dict(depth=1,library=chosen,partial=True))
def attribution(v):
    b=v['constructor_births'];is_visible={ref for ref,t,h in b['endpoint'] if not h}
    paid={x['allocated']<<32 for x in v['merge_child']['issued'] if x['allocated'] is not None}
    root={r[2]:r for r in v['root_recipe']['commits']}
    result=v['strict_named'] or {};links={child:(src,depth) for child,src,depth in result.get('links',[])}
    assert len(links)==result.get('counts',{}).get('source_commits',0)
    for child,(parent,depth) in links.items():
        assert parent in root and parent not in links and root[child][5]>root[parent][5] and depth in (1,2)
    glob=Counter();internal=Counter();owners=set();total=0;surviving=0
    for ref,t,ep,ctor,serial,ancestor,cross,flags in b['rows']:
        if not ctor or not serial or not flags&1:continue
        assert serial in root
        kind='paid' if ref in paid else 'dynamic' if flags&2 else 'typed'
        glob[kind+'.new']+=1;glob[kind+'.visible']+=int(ref in is_visible)
        total+=1;surviving+=int(ref in is_visible)
        if serial in links:
            internal[kind+'.new']+=1;internal[kind+'.visible']+=int(ref in is_visible)
            if kind=='typed' and ref in is_visible:owners.add(links[serial][0])
    return dict(births=total,visible=surviving,global_kinds=dict(glob),internal_kinds=dict(internal),distinct_roots_with_internal_visible_typed=len(owners),
                link_depth=dict(Counter(d for _,d in links.values())),birth_digest=digest(b['rows']),endpoint_digest=digest(b['endpoint']))
def collect_audit(v,mode,receipt,lookup):
    signed=v['strict_named'] or {}
    rows=signed.get('signed_commits',[]);short=signed.get('links',[])
    assert len(rows)==len(short)
    origin={r[2]:r for r in v['root_recipe']['commits']}
    visible={x[0]for x in v['constructor_births']['endpoint'] if not x[2]}
    extras={c["allocated"]<<32 for c in v["merge_child"]["issued"] if c["allocated"] is not None}
    effect={row[0]:[0]*6 for row in rows}
    for fid,table,epoch,constructor,ticket,_,_,flags in v['constructor_births']['rows']:
        if ticket not in effect or not constructor or not flags&1:continue
        i=4 if fid in extras else 2 if flags&2 else 0
        effect[ticket][i]+=1;effect[ticket][i+1]+=int(fid in visible)
    ids=[]
    for row,shortrow in zip(rows,short):
        child,root,path,trail,run=row;assert [child,root,len(path)]==shortrow
        assert len(path)==len(trail)>0 and origin[root][3]==path[0][0] and origin[child][3]==path[-1][2]
        for i,(edge,port) in enumerate(zip(path,trail)):
            assert edge[1]==port[1] and port[3]<run
            if i:assert path[i-1][2]==edge[0] and trail[i-1][3]<port[3]
        decoded=row+[effect[child]]
        code=json.dumps(decoded,separators=(',',':'))
        if code not in lookup:
            lookup[code]=len(receipt['records']);receipt['records'].append(decoded)
        ids.append(lookup[code])
    receipt['arms'][mode]=ids

def check(r):
    base=r['leaf']
    for n in MODES:
        q=r[n]
        for k in KEYS:assert q[k]==base[k],(n,k)
        assert q['aligned'] and all(q['checks'].values())
        assert q['packets']==sum(q['emitted'])+q['paid_tokens'] and q['fept']==q['visible']/q['packets']
        if n=='leaf':continue
        c=q['counts'];p=q['partition']
        assert c['released']==c['actual_internal']==c['source_commits']+q['uncommitted']==base['emitted'][0]-q['emitted'][0]
        assert p['excluded_metadata_rows']==p['signed_children']==p['child_logits_for_audit']
        assert p['residual_bank_rows']==p['excluded_metadata_rows']+p['residual_scored']
        if n in ('partial','partial2','donor_partial'):assert p['mixed_with_external']>0
    assert r['partial']['packets']<r['whole']['packets'] and r['donor_partial']['packets']<r['donor_whole']['packets']
    assert r['faults']['stale_reverts'] and r['faults']['wrong_port']
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);report={};links={}
    for case in a.cases:
        prog,plan,req=src.config(a,case);opts=options(prog);vd=a.exp/'compact-vanilla-20261121'
        with src.base.session(vd/'vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={};receipt={'records':[],'arms':{}};lookup={}
        for n,opt in opts.items():
            opts_a=dict(opt,record_links=True)
            with src.base.session(a.native,prog,plan) as get:v=get(dict(driver['filtered'](req,opts_a),audit=True,birth_ledger=True))
            assert 'source_error' not in v,(n,v.get('source_error'))
            q=src.base.summarize(v,gold);del q['work'],q['rows'];q.update(attribution(v))
            signed=v['strict_named'] or {};c=signed.get('counts',{});q.update(counts=c,partition=signed.get('partition',{}),availability=signed.get('availability',{}),
                 uncommitted=signed.get('uncommitted',0),regular_checks=v['single']['work'][2],all_single=digest(v['single']['committed']),
                 audit_score=v['single']['adaptive_rows']['decision_digest'],paid_choices=len(v['merge_child']['issued']),
                 paid_tokens=sum(int(x['selected'])for x in v['merge_child']['issued']),ms=[],wall_ms=[])
            q['packets']=sum(q['emitted'])+q['paid_tokens'];q['fept']=q['visible']/q['packets']
            collect_audit(v,n,receipt,lookup)
            rows[n]=q;print(case,n,q['emitted'],q['fept'],q['internal_kinds'],q['partition'],flush=True)
            del v
        opt=opts['partial']
        with src.base.session(a.native,prog,plan) as get:v=get(dict(driver['filtered'](req,dict(opt,stale_versions=True,record_links=True)),audit=True))
        assert 'source_error' not in v,v.get('source_error')
        b=src.base.summarize(v,gold)
        for k in ('checks','physical','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','rhs','state_sha','commits','emitted','raw','wire_bytes'):
            assert b[k]==rows['leaf'][k],k
        rows['faults']=dict(stale_reverts=v['strict_named']['counts']['source_commits']==0 and v['strict_named']['partition']['stale_refs']>0,
                            stale_skipped=v['strict_named']['partition']['stale_refs'])
        with src.base.session(a.native,prog,plan) as get:f=get(driver['filtered'](req,dict(opt,wrong_port=True)))
        rows['faults'].update(wrong_port=f.get('source_error')=='strict named return port corruption',failed_run=f['runs'])
        check(rows)
        with src.base.session(a.native,prog,plan) as infer:
            for lap in range(a.repeats+1):
                names=list(MODES);seq=names[lap%len(names):]+names[:lap%len(names)]
                for n in seq if lap%2 else reversed(seq):
                    start=perf_counter();v=infer(driver['filtered'](req,opts[n]));wall=1000*(perf_counter()-start)
                    assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha'] and v['root_recipe']['emitted']==rows[n]['emitted']
                    if n!='leaf':
                        c=v['strict_named']['counts'];p=v['strict_named']['partition']
                        assert c['audit_score_inputs']==p['child_logits_for_audit']==0 and p['production_virtual']==p['signed_children']
                        assert c['source_commits']==rows[n]['counts']['source_commits']
                        rows[n]['production_counts']=c;rows[n]['production_partition']=p
                    if lap:rows[n]['ms'].append(v['ms']);rows[n]['wall_ms'].append(wall)
        for n in MODES:rows[n]['median_ms']=median(rows[n]['ms']);rows[n]['median_wall_ms']=median(rows[n]['wall_ms'])
        links[case]=receipt;(a.out/'signed_commits.json').write_text(json.dumps(links,separators=(',',':'))+'\n')
        report[case]=rows;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(n,round(rows[n]['median_ms'],2))for n in MODES],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
