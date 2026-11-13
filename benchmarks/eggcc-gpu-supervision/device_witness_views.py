"""Transient constructor views projected from authoritative Cell slots.

No persistent field registry is added. Missing/lost coverage blocks allocation;
view completeness is relative to resident Cells and an explicit external-coverage
and settled-Eq guarantee from the surrounding runtime.
"""
import numpy as np


def compile_view(recipe,table_id,arity):
    name=recipe['tables'][table_id]['name'];records=[]
    for rid,rule in enumerate(recipe['rules']):
        occurrences=[]
        for atom in rule['query']:
            if atom['call'].get('table')==name:
                occurrences.append((-1,atom['args'][:-1],atom['args'][-1]))
        for oi,op in enumerate(rule['effects']):
            if op.get('call',{}).get('table')==name and op['kind'] in ('construct','set'):
                occurrences.append((oi,op['args'],dict(slot=op['dst']) if op['kind']=='construct' else op['value']))
        for oi,args,result in occurrences:
            operands=[*args,result]
            supported=len(args)==arity and all('slot' in a for a in operands)
            refs=[a['slot'] for a in operands if 'slot' in a]
            overwritten=[j for j,op in enumerate(rule['effects']) if j>oi and op.get('dst') in refs]
            records.append(dict(rule=rid,after=oi+1,expires=min(overwritten)+1 if overwritten else len(rule['effects'])+1,
                effect_count=len(rule['effects']),supported=supported,
                slots=[a['slot'] for a in operands] if supported else [0]*(arity+1)))
    if not records:
        records=[dict(rule=-1,after=0,expires=1,effect_count=0,supported=False,slots=[0]*(arity+1))]
    return dict(table=table_id,arity=arity,
        **{k:np.array([r[k] for r in records],np.int32) for k in ('rule','after','expires','effect_count','slots')},
        supported=np.array([r['supported'] for r in records],bool))


def project(state,plan,external_complete,eq_settled,xp,include_fields=False):
    rows=state['slots'].shape[0];records=plan['rule'].shape[0]
    associated=(state['present'][:,None] & state['visible'][:,None]
                & (state['keys'][:,0,None]==plan['rule'][None,:]))
    pc=xp.where(state['settled'][:,None],plan['effect_count'][None,:],state['effect_pc'][:,None])
    exists=associated & (pc>=plan['after'][None,:])
    not_overwritten=pc<plan['expires'][None,:]
    slots=state['slots'][:,plan['slots']]
    roots=state.get('slot_roots',state['slots'])[:,plan['slots']]
    available=xp.all(state['slot_valid'][:,plan['slots']],axis=2)
    live=exists & not_overwritten & available & plan['supported'][None,:]
    lost=exists & ~live
    # Missing observed data is unknown, not evidence the constructor is absent.
    complete=external_complete & eq_settled & ~xp.any(lost)
    keys=xp.concatenate([xp.full((rows,records,1),plan['table'],dtype=state['slots'].dtype),roots[:,:,:-1]],axis=2)
    ids=slots[:,:,-1]
    result=dict(keys=keys.reshape(rows*records,plan['arity']+1),ids=ids.reshape(-1),
        roots=roots[:,:,-1].reshape(-1),live=live.reshape(-1),complete=complete,
        missing=lost.reshape(-1))
    if include_fields:
        result.update(values=slots.reshape(rows*records,plan['arity']+1),value_roots=roots.reshape(rows*records,plan['arity']+1),
            source=xp.broadcast_to(xp.arange(rows)[:,None],(rows,records)).reshape(-1),
            record=xp.broadcast_to(xp.arange(records)[None,:],(rows,records)).reshape(-1),
            source_slots=xp.broadcast_to(plan['slots'][None,:,:],(rows,records,plan['arity']+1)).reshape(rows*records,plan['arity']+1))
    return result


def main():
    import argparse,hashlib,json
    from pathlib import Path
    from collect_observed_corpus import read_bytes
    from compile_constructor_sites import compile_sites
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.source);recipe=json.loads(raw)['recipe'];sites=compile_sites(recipe)['sites']
    layouts=[compile_view(recipe,t,n) for t,n in sorted({(s['table'],len(s['args'])) for s in sites})]
    result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),table_arity_layouts=len(layouts),
        static_records=sum(len(p['rule']) for p in layouts),
        supported_records=sum(int(p['supported'].sum()) for p in layouts),
        unknown_records=sum(int((~p['supported']).sum()) for p in layouts),
        static_array_bytes=sum(v.nbytes for p in layouts for v in p.values() if isinstance(v,np.ndarray)),
        scope='Static recipe projection layouts; no runtime witness-completeness or speed result',
        persistent_fact_registry_added=False,external_coverage_required=True,settled_eq_required=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
