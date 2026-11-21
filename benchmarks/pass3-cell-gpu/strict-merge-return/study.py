"""Run the same filtered explicit-parent leaf with/without a preissued static merge child."""
import argparse,hashlib,json
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
mod=run_path(str(HERE/'measure.py'));src=mod['src'];filtered=mod['filtered']['filtered']
def h(x):return hashlib.sha256(json.dumps(x,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def addr(dep):
    assert 'Fact' in dep
    v=dep['Fact'];return(v['cell']<<32)|v['op']

def read_ledger(v,gold):
    assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','state_sha','runs'))
    trace=v['events'];unions=[[e for e in run if e[0]=='union'] for run in trace]
    root=v['root_recipe'];m=v['merge_child'];branches=m['issued'];b=v['constructor_births']
    roots={row[0]:row for row in root['commits']};assert len(roots)==gold['rhs_count']==root['applied']
    old={(c['parent']['ordinal'],c['effect']):c for c in branches}
    assert len(old)==len(branches) and len(branches)==m['counts'][0]
    rows={f:(ep,t,serial,flags) for f,t,ep,ctor,serial,anc,cross,flags in b['rows'] if ctor and serial and flags&1}
    visible={f for f,t,hidden in b['endpoint'] if not hidden}
    actual=v['strict_merge'];packets=sum(root['emitted'])+sum(c['selected'] for c in branches)
    q={'runs':v['runs'],'rhs_count':len(roots),'emitted_roots':root['emitted'],'selected_children':sum(c['selected'] for c in branches),
       'child_candidates':len(branches),'external_child_fresh':m['counts'][5],'packets':packets,
       'owned_births':len(rows),'effective_births':len(rows.keys()&visible),'fept':len(rows.keys()&visible)/packets,
       'strict':actual['counts'],'plans':actual['plans'],'state_sha':v['state_sha'],
       'digests':{k:h(v[k]) for k in ('rhs','writes','resumes','cell_ids','allocations')},
       'root_commits_sha':h(root['commits']),'root_fresh_sha':h(root['fresh']),'unions_sha':h(unions),
       'events_sha':h(trace),'birth_sha':h(b['rows']),'export_original_sha':h(b['endpoint']),'coalesced_sha':h(b['coalesced']),
       'compiled_rules':len(actual['plans']),'ms':[],'wall_ms':[]}
    return q,old,rows,visible,roots

def verify_internal(v,base,old,rows,visible,roots):
    st=v['strict_merge'];plans=dict(st['plans']);ev=st['events']
    keyed={(e[0],e[3]):e for e in ev};assert len(keyed)==len(ev)==st['counts']['entered']
    missing=base.keys()-old.keys();assert old.keys()<=base.keys()
    for k,c in old.items():
        a=base[k];assert all(a[f]==c[f] for f in ('parent','effect','constructor','old_reference','old_epoch','candidate_reference',
                                                  'candidate_site','old','new','selected','reused','allocated','rejected','returned_reference')),(k,c)
    internal_visible=internal_fresh=interned=factory_born_here=0;notes=[]
    primary_by_ordinal={r[1]:r[0] for r in v['root_recipe']['fresh']}
    for k in missing:
        c=base[k];original=roots[k[0]];p=plans[original[3]]
        assert any(w['atom']==p['old_atom'] and c['old_reference']==w['row'] and w['version']==c['old_epoch'] for w in original[6])
        if k not in keyed:
            assert c['allocated'] is None and not c['reused']
            continue
        e=keyed[k];ordn,serial,rid,effect,oldref,ver,candidate,ctor,result,fresh=e
        assert original[2:4]==[serial,rid] and c['old_reference']==oldref and c['old_epoch']==ver
        assert c['constructor']==ctor==p['constructor'] and p['factory']==c['candidate_site'] and c['candidate_reference']==candidate
        candidate_id=addr(candidate)
        factory_born_here+=int(candidate_id>>32==primary_by_ordinal.get(ordn) and candidate_id&0xffffffff==p['factory']
                               and candidate_id in rows and rows[candidate_id][2]==serial)
        assert c['returned_reference']==result,(k,c['returned_reference'],result)
        if fresh:
            assert c['allocated'] is not None and addr(result)==c['allocated']<<32
            fid=addr(result);assert rows[fid][1:3]==(ctor,serial) and rows[fid][3]&2
            internal_fresh+=1;internal_visible+=fid in visible
        else:
            assert c['reused'];interned+=1
        if len(notes)<4:notes.append({'ordinal':ordn,'root':serial,'old_fact':oldref,'old_version':ver,'factory_actual_return':candidate,
                                      'nested_actual_return':result,'new_nested_constructor':fresh})
    assert set(keyed)=={k for k in missing if base[k]['allocated'] is not None or base[k]['reused']},(len(keyed),len(missing))
    assert internal_fresh==st['counts']['fresh'] and interned==st['counts']['interned']
    return {'suppressed_child_scores':len(missing),'suppressed_child_proposals':sum(base[k]['selected'] for k in missing),
            'internal_fresh':internal_fresh,'internal_interned':interned,'internal_visible':internal_visible,'verified_leaf_physical_returns':len(keyed),'factory_fresh_on_root':factory_born_here,'factory_returned_existing':len(keyed)-factory_born_here,'examples':notes}

def main(a):
    a.out.mkdir(parents=True,exist_ok=True);result={}
    for case in a.cases:
        prog,plan,req=src.config(a,case);cfg=filtered(req,{'depth':0})
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as oracle:gold=oracle({'audit':True})
        with src.base.session(a.native,prog,plan) as run:
            arms={}
            for n,mode in (('leaf',0),('composed',1)):
                v=run(dict(cfg,audit=True,birth_ledger=True,strict_merge=mode));assert 'source_error' not in v,(case,n,v.get('source_error'))
                q,ch,b,seen,roots=read_ledger(v,gold);arms[n]=q
                if mode==0:base=ch
                else:
                    q['internal']=verify_internal(v,base,ch,b,seen,roots)
                    for k in ('runs','rhs_count','emitted_roots','owned_births','effective_births','digests','state_sha','root_commits_sha',
                              'root_fresh_sha','unions_sha','events_sha','birth_sha','export_original_sha','coalesced_sha'):assert q[k]==arms['leaf'][k],(case,k)
                    assert q['packets']+q['internal']['suppressed_child_proposals']==arms['leaf']['packets']
                print(case,n,q['packets'],q['fept'],q['strict'],flush=True);del v
            faults={}
            for mode in (2,3):
                v=run(dict(cfg,audit=False,strict_merge=mode));assert 'strict merge old reference differs' in v.get('source_error','') and v['runs']<gold['runs'],v.get('source_error')
                faults[str(mode)]=[v['runs'],v['source_error']]
            if not a.smoke:
                for lap in range(1+a.repeats):
                    names=[('leaf',0),('composed',1)]
                    for n,m in names if lap%2 else reversed(names):
                        t=perf_counter();v=run(dict(cfg,strict_merge=m));wall=1000*(perf_counter()-t)
                        assert 'source_error' not in v and v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                        assert v['strict_merge']['counts']==arms[n]['strict'] and v['root_recipe']['emitted']==arms[n]['emitted_roots']
                        if lap:arms[n]['ms'].append(v['ms']);arms[n]['wall_ms'].append(wall)
                for v in arms.values():v.update(median_ms=median(v['ms']),median_wall_ms=median(v['wall_ms']))
        result[case]={'arms':arms,'faults':faults};(a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4);p.add_argument('--smoke',action='store_true')
    a=p.parse_args();a.seed=1703;a.cap=8192;main(a)
