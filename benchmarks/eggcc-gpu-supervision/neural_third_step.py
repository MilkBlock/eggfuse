"""Differentiable replay of actual device-selected post-transfer Cell inputs.

Synthetic instances only. Exact completion builds routing and independent labels;
no reference token or Eq label is an input to the learned third transition.
"""
import argparse,json,time,hashlib
from pathlib import Path
from copy import deepcopy
from collections import Counter
import numpy as np
import mlx.core as mx
from audit_neural_gpu_rhs import initial_case
from audit_snapshot_queries import device
from neural_cell_samples import samples,apply_instance
from neural_cell_chains import chains,completed
from neural_device_candidates import compile_frames,seed_inputs,compile_candidates,candidates
from device_constructor_completion import complete
from neural_owner_handoff import handoff
from reference_cell_closure import facts_from_cells
from reference_union_family import compare_graph
from neural_eq_readout import targets
from train_neural_cell_chains import incoming_tokens


def replay(model,batch):
    p={k[2:]:v for k,v in batch.items() if k.startswith('p_')}
    c={k[2:]:v for k,v in batch.items() if k.startswith('c_')}
    _,first=model(p['x'],p['edges'],p['mask'],p['request'],p['relations'])
    _,second=model.transition(incoming_tokens(model,c,first),c['edges'],c['mask'],c['request'],c['relations'])
    boundary=model.encode(batch['seed_x'])
    incoming=mx.where((batch['source_kind']==1)[...,None],first[:,None,:],boundary)
    incoming=mx.where((batch['source_kind']==2)[...,None],second[:,None,:],incoming)
    return model.transition(incoming,batch['edges'],batch['mask'],batch['request'],batch['relations'])


def valid_candidate(relation,key,expected):
    half=len(relation)//2
    return bool(np.all((relation[half:]==0)|(relation[:half]>0))) and key in expected


def fingerprints(data):
    keys=sorted(k for k in data if k not in ('eq_target','eq_mask','valid','case','rule'))
    result=[]
    for i in range(len(data['valid'])):
        parts=[]
        for k in keys:
            v=data[k][i]
            if k=='seed_x':v=np.where(((data['source_kind'][i]==0)&data['mask'][i])[...,None],v,0)
            if k=='c_seed_x':v=np.where((~data['c_replace'][i]&data['c_mask'][i])[...,None],v,0)
            parts.append(v.tobytes())
        result.append(hashlib.sha256(b''.join(parts)).digest())
    return result


def build(recipe,count,seed,per_pair=2):
    records=[];base=samples(recipe,count,seed,records,ordered=True);transfers=[]
    chain,_=chains(recipe,records,ordered=True,transfers=transfers)
    selected=[];pairs=Counter()
    for record in transfers:
        i=record['chain'];pair=(int(chain['producer'][i]),int(chain['consumer'][i]))
        if pairs[pair]<per_pair:selected.append(record);pairs[pair]+=1
    items=[];moved=0;width=max(len(r['slots']) for r in recipe['rules']);field_width=base['x'].shape[-1]//128
    for case,record in enumerate(selected):
        i=record['chain'];local,host,cp,ctx,tp,src,dst,seed_count,oracle=initial_case(recipe,record)
        state=device(host);frames=device(compile_frames(local,host['owner_projection'].shape[1]))
        raw,_=seed_inputs(state,frames,mx,field_width);mx.eval(raw)
        registry=device(ctx);next_id=mx.array(seed_count);settled=mx.array(True)
        for _ in range(2):
            state,next_id,marks=complete(state,device(cp),next_id,mx.array(len(ctx['roots'])),mx.array(64),mx.array(True),settled,mx,registry,eq_rounds=8)
            registry=marks['eq_context'];settled=marks['eq_settled']
        if bool(marks['needs_attention']):raise ValueError('unsettled synthetic completion')
        if tp['covered']:
            state,move=handoff(state,device(tp),mx.array(src),mx.array(dst),mx.array(1),mx.array(1),mx.array(1.),mx.zeros(128),mx.array(True),mx.array(True),mx)
            moved+=bool(move['transferred'])
        mx.eval(state)
        facts,covered=facts_from_cells(local,{k:np.array(v) for k,v in state.items()})
        check=compare_graph(oracle,facts,np.array(registry['roots'])[:int(next_id)],seed_count,include_mapping=True)
        if not covered or not check['passed']:raise ValueError('synthetic device/oracle mismatch')
        mapping=check['mapping']
        for rid,rule in enumerate(recipe['rules']):
            plan=compile_candidates(local,rule,atoms=base['x'].shape[1],fields=field_width)
            b=candidates(state,frames,device(plan),mx.array(True),mx.array(True),mx);mx.eval(b)
            if not bool(b['complete']):raise ValueError('incomplete synthetic candidate enumeration')
            expected={tuple(sorted(v.items())) for v in oracle.matches(rule)}
            for j in np.flatnonzero(np.array(b['live'])):
                sources=np.array(b['sources'][j]);mask=np.array(b['mask'][j]);kind=np.where(sources==dst,2,np.where(sources==src,1,0)).astype(np.int32)
                # Only actual snapshot seeds may be encoded. Source/target use
                # their generated tokens irrespective of physical slot owner.
                for address,k,active in zip(sources,kind,mask):
                    if active and k==0 and not bool(frames['seed'][state['keys'][address,0]]):raise ValueError('unknown token lineage')
                key=tuple((slot,mapping.get(int(root),-1)) for slot,root in zip(plan['inputs'],np.array(b['binding_roots'][j])))
                valid=valid_candidate(np.array(b['relations'][j]),key,expected)
                eq=dict(eq_target=np.zeros(width*(width-1)//2,np.float32),eq_mask=np.zeros(width*(width-1)//2,bool))
                if valid:
                    ref=deepcopy(oracle);bound=dict(key);apply_instance(ref,rule,bound)
                    eq=targets(rule,completed(rule,bound,ref),ref,width)
                datum={k:np.array(b[k][j]) for k in ('edges','mask','request','relations')}
                datum.update(seed_x=np.array(raw)[sources],source_kind=kind,valid=np.float32(valid),rule=np.int32(rid),case=np.int32(case),**eq)
                datum.update({'p_'+k:base[k][chain['parent'][i]] for k in ('x','edges','mask','request','relations')})
                datum.update({'c_'+k:chain[k][i] for k in ('seed_x','replace','edges','mask','request','relations')})
                items.append(datum)
        print(json.dumps(dict(case=case+1,total_cases=len(selected),candidates=len(items))),flush=True)
    if not items:raise ValueError('empty replay dataset')
    data={k:np.array([v[k] for v in items]) for k in items[0]}
    report=dict(synthetic_only=True,seed=seed,source_samples_per_rule=count,per_pair=per_pair,cases=len(selected),physical_transfers=moved,candidates=len(items),valid=int(data['valid'].sum()),generated_target_inputs=int(((data['source_kind']==2)&data['mask']).any(axis=1).sum()),token_targets_used_as_inputs=False,scope='bounded synthetic exact-completion routing, differentiable three-step token replay; not autonomous saturation')
    return data,report


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);p.add_argument('--seed',type=int,default=23001);p.add_argument('--count',type=int,default=4);p.add_argument('--per-pair',type=int,default=2);a=p.parse_args()
    if min(a.count,a.per_pair)<1:raise ValueError('positive sample counts required')
    source=json.loads(a.trace.read_text());source=source.get('recipe',source);recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    began=time.perf_counter();data,report=build(recipe,a.count,a.seed,a.per_pair)
    np.savez_compressed(a.output,**data);report.update(wall_seconds=time.perf_counter()-began,recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),dataset_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())
    a.output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
