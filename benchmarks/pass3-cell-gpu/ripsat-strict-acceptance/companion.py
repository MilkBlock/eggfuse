"""Extract the next original paid read of the exact *already authenticated* middle Set publication."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
from runpy import run_path
import argparse,json
HERE=Path(__file__).resolve().parent
core=run_path(str(HERE/'chain_audit.py'));src=core['src'];cap=run_path(str(HERE.parent/'ripsat-donor-evidence/capture.py'))
digest=cap['digest'];file_sha=lambda f:sha256(f.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())
def key(d):return core['fact'](d['row'])

def ground_bank(program):
    terms=cap['Terms']();tables=program['recipe']['tables'];idx={t['name']:i for i,t in enumerate(tables)}
    ids={};events=[]
    for r in program['initial']:
        vals=[]
        for v in r['values']:
            if 'eq' in v:vals.append({'Eq':ids.setdefault((v['sort'],v['eq']),len(ids)+1)})
            elif v['sort']=='String':vals.append({'Text':v['value']})
            elif v['sort'] in ('i64','bool','Unit'):vals.append({'Int':int(v.get('value') or 0)})
            else:vals.append({'Unrepresented':v.get('value')})
        if not r.get('subsumed'):events.append(['birth',idx[r['table']],vals[:-1],vals[-1],-1,None])
    for _ in range(4):
        for e in events:terms.event(e,tables)
    return terms,tables,idx

def main(a):
    base=read(a.evidence);trust_path=HERE.parent/'ripsat-donor-evidence/trust.json';trust=read(trust_path)
    assert file_sha(a.evidence)==trust['manifest_sha256'];a.out.mkdir(exist_ok=True,parents=True);result={}
    donors=core['bridge']['donor_paths'](a.donor)
    for name in ('dot-product','jacobi-1d'):
        sid=f'{name}-p143-o1-c55-full';item=next(s for s in base['donors'][name]['samples'] if s['sample_id']==sid)
        def artifact(relative):
            v=item['artifacts'][relative];p=a.evidence.parent/v['path'];assert file_sha(p)==v['sha256'];return p
        orig=read(artifact('origin.json'))['sample'];middle=orig['consumer'];middle_serial=middle['serial']
        p,plan,req=src.config(a,name);pr=read(p)
        lib=core['adapter']['compile_library'](a.evidence,donors,p)
        def config(spec):
            cfg=core['bench']['bake'].settings(req,dict(spec,partial=True,record_links=True))
            return dict(cfg,rows=dict(cfg["rows"],scalar_certificates=True),integral_root="off",integral_packets=False,audit=True,birth_ledger=True)
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as exact:gold=exact({'audit':True})
        with src.base.session(a.native,p,plan) as execute:
            leaf=execute(config({'depth':0}));signed=execute(config(lib['strict_named']))
        for v in (leaf,signed):assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','runs','state_sha'))
        assert all(leaf[k]==signed[k] for k in ('cell_ids','allocations','schedule'))
        assert leaf['root_recipe']['commits']==signed['root_recipe']['commits']
        assert leaf['constructor_births']==signed['constructor_births'] or all(leaf['constructor_births'][k]==signed['constructor_births'][k] for k in ('rows','endpoint','coalesced'))
        filtered_events=lambda v:[[e for e in row if not e[0].startswith('observed-signed-')] for row in v['events']]
        assert filtered_events(leaf)==filtered_events(signed)
        roots={r[2]:r for r in leaf['root_recipe']['commits']};births=leaf['constructor_births']['rows'];L={r[0]:r for r in signed['strict_named']['signed_commits']}
        mid=roots[middle_serial];first=roots[orig['producer']['serial']];assert mid[0]==middle['ordinal'] and mid[3]==55 and mid[5]==middle['epoch']
        assert L[middle_serial][1]==first[2] and L[middle_serial][2]==[[143,1,55]]
        assert mid[6]==[r['named'] for r in middle['rows']]
        born,=[(fid,t,ep) for fid,t,ep,ctor,s,anc,cross,flags in births if s==middle_serial and ctor and flags&1 and not flags&2 and (fid&0xffffffff)==1]
        fid,table,ep=born;assert ep==mid[5] and pr['recipe']['tables'][table]['name']=='Get'
        children=[r for r in roots.values() if r[3]==143 and r[5]>ep and r[0]>mid[0] and any(key(w)==fid and w['atom']==0 and w['version']==ep for w in r[6])]
        matching_events=[e for row in leaf['events'] for e in row if e[0]=='birth' and e[4]==fid]
        event,=matching_events;assert event[1]==table and event[5][1]==55
        # The portable source history includes true signed parent/child physical refs, not only names.
        physical={s:{'root_ordinal':o,'rule':rid,'template':t,'epoch':run,'refs':refs,'slot_values':vals}
                  for o,provider,s,rid,t,run,refs,vals in (first,mid,*children)}
        record={'donor':name,'source_sample_id':sid,'program_sha256':file_sha(p),'recipe_sha256':pr['recipe']['sha256'],
                'source_origin_sha256':file_sha(artifact('origin.json')),'native_acceptance_sha256':file_sha(artifact('native/acceptance.json')),
                'native_history_sha256':file_sha(artifact('native/history.json')),'trust_index_sha256':file_sha(trust_path),
                'reference':dict(runs=gold['runs'],rhs=gold['rhs_count'],state_sha=gold['state_sha'],rhs_sha=digest(gold['rhs']),
                                 writes_sha=digest(gold['writes']),resumes_sha=digest(gold['resumes']),events_sha=digest(filtered_events(leaf)),
                                 physical_sha=digest(leaf['cell_ids']),root_commits_sha=digest(leaf['root_recipe']['commits'])),
                'first_origin_sample':orig,'middle_signed_trail':L[middle_serial],'original_committed_roots':physical,
                'middle_set_fact':fid,'set_version':ep,'middle_set_birth_event':event,
                'later_143_paid_serials':[r[2] for r in children if r[2] not in L],'later_143_internal_serials':[r[2] for r in children if r[2] in L],
                'companions':[]}
        assert not record['later_143_internal_serials']
        terms,tables,idx=ground_bank(pr)
        for step,events in zip(leaf['schedule'],leaf['events']):
            epoch=step[1]
            for child in children:
                if child[5]!=epoch:continue
                rule=pr['recipe']['rules'][child[3]];atom=rule['query'][0];cols=[child[7][str(a['slot'])] for a in atom['args']]
                name_t=atom['call']['table'];assert name_t=='Get'
                g=[terms.read(v,s['name']) for v,s in zip(cols[:-1],tables[idx[name_t]]['schema'])]
                assert all(v is not None for v in g),'the nominated terminal has no traced representative'
                w,=child[6];assert key(w)==fid and w['version']==ep
                child_row=dict(atom=0,table=name_t,values=cols,named=w,terms=[x[1] for x in g],size=sum(x[0] for x in g))
                terminal=dict(rule=child[3],fingerprint=cap['rule_sig'](rule),source_name=rule['metadata']['name'],ruleset=rule['metadata']['source_set'],
                              epoch=child[5],ordinal=child[0],serial=child[2],rows=[child_row])
                record['companions'].append(dict(producer=middle,consumer=terminal,producer_op=1,consumer_atom=0,
                         original_fact=fid,original_version=ep,birth_event=event,relative_runs=child[5]-ep,support=len(children)))
            for e in events:terms.event(e,tables)
        assert len(children)==len(record['companions'])
        target=a.out/(name+'-same-middle.json');target.write_text(json.dumps(record,indent=1)+'\n')
        result[name]=dict(file=target.name,sha256=file_sha(target),source_sample=sid,middle=middle_serial,fact=fid,version=ep,
                          later_143=record['later_143_paid_serials'],internal=record['later_143_internal_serials'])
        print(name,result[name],flush=True)
    (a.out/'companion-pins.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','evidence','out'):p.add_argument(k,type=Path)
    p.add_argument('--donor',action='append',required=True);a=p.parse_args();a.seed=1703;a.cap=8192;main(a)
