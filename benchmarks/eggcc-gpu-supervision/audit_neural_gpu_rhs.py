"""GPU exact target completion followed by neural-token ownership handoff.

Independent synthetic initial snapshots; CPU never fills target RHS slots.
The neural output stays dense. Existing exact GPU kernels supply constructor
identity, copy and union side metadata. This is not a full stage runtime.
"""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from neural_cell_samples import samples,apply_instance
from neural_cell_chains import chains,completed
from neural_ordered_relations import OrderedCellTransition
from lower_constructor_sets import lower
from device_snapshot_import import prepare_family,identity,eq_registry
from device_constructor_completion import compile_completion,complete
from device_slot_owners import pack,read,compile_transfer,COLUMNS
from neural_owner_handoff import handoff
from reference_union_family import Reference,compare_graph
from reference_cell_closure import facts_from_cells
from audit_snapshot_queries import device
from multi_entry_ridge import scalar


def initial_case(recipe,record):
    oldplan=record['plan'];ref=record['initial_reference']
    original=dict(recipe,rules=[recipe['rules'][oldplan['producer']],recipe['rules'][oldplan['consumer']]])
    lowered,_=lower(original)
    def value(v):
        v=ref.root(v)
        return dict(sort=ref.types[v],eq=str(v)) if ref.types[v] is not None else ref.scalar_values[v]
    snapshot=dict(rows=[dict(table=t,values=[value(v) for v in vs],subsumed=False) for t,vs in sorted(ref.normalized_facts())])
    local,state,ids,rows=prepare_family(lowered,snapshot,[0,1],2)
    full_lowered,_=lower(recipe);width=max(len(r['slots']) for r in full_lowered['rules'])
    current=state['slots'].shape[1]
    for column in COLUMNS:
        if column not in state:continue
        v=state[column];extra=np.full((len(v),width-current)+v.shape[2:],-1 if column in ('slots','slot_roots') else 0,v.dtype)
        state[column]=np.concatenate([v,extra],axis=1)
    source,target=len(rows),len(rows)+1
    source_values=completed(local['rules'][0],record['source_binding'],ref)
    binding={s:ids[identity(value(v))] for s,v in record['initial_binding'].items()}
    for address,rid,values in ((source,0,{s:ids[identity(value(v))] for s,v in enumerate(source_values)}),(target,1,binding)):
        state['keys'][address,0]=rid;state['generation'][address]=1
        state['present'][address]=state['visible'][address]=True
        state['active'][address]=address==target;state['settled'][address]=address==source
        state['effect_pc'][address]=len(local['rules'][rid]['effects']) if address==source else 0
        for slot,v in values.items():
            state['slots'][address,slot]=state['slot_roots'][address,slot]=v;state['slot_valid'][address,slot]=True
            # All scalar values are initial input, never effect outputs.
            val=json.loads(next(k for k,i in ids.items() if i==v))
            if 'eq' not in val:state['scalar_codes'][address,slot]=scalar(val);state['scalar_valid'][address,slot]=True
        inputs=[s for s,d in enumerate(local['rules'][rid]['slots']) if d['definition']=='query']
        for i,s in enumerate(inputs):state['keys'][address,i+1]=values[s]
    target_effect_slots=[s for s,d in enumerate(local['rules'][1]['slots']) if d['definition']!='query']
    if state['slot_valid'][target,target_effect_slots].any():raise AssertionError('CPU prefilled a target RHS slot')
    inverse={int(dst):int(src) for src,dst in enumerate(oldplan['projection']) if oldplan['required'][src] and not oldplan['copied'][src]}
    inputs=[s for s,d in enumerate(local['rules'][1]['slots']) if d['definition']=='query']
    transfer_plan=compile_transfer(local,dict(producer=0,consumer=1,projection=[inverse.get(s,0) for s in inputs],projection_valid=[s in inverse for s in inputs]),width)
    completion=compile_completion(local,width,include_unions=True);completion['retain_predicted_rules']=(0,1)
    if completion['marks']:raise ValueError(completion['marks'])
    registry=eq_registry(ids,completion['eq_sort_names'],reserve=64)
    # Independent source operations execute only in the CPU audit oracle.
    oracle=Reference(original,rows,ids);apply_instance(oracle,original['rules'][1],binding)
    return local,pack(state),completion,registry,transfer_plan,source,target,len(ids),oracle


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--limit',type=int,default=8);a=p.parse_args()
    if a.limit<1:raise ValueError('positive case budget required')
    raw=json.loads(a.trace.read_text());source=raw.get('recipe',raw);recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    started=time.perf_counter();records=[];base=samples(recipe,4,93003,records,ordered=True);transfers=[]
    chain,_=chains(recipe,records,ordered=True,transfers=transfers)
    model=OrderedCellTransition(base['x'].shape[-1],base['relations'].shape[-1]);model.load_weights(str(a.weights))
    parent=device({k:v[chain['parent']] for k,v in base.items()});dc=device(chain)
    first,source_tokens=model(parent['x'],parent['edges'],parent['mask'],parent['request'],parent['relations'])
    incoming=mx.where(dc['replace'][...,None],source_tokens[:,None,:],dc['tokens'])
    logits,tokens=model.transition(incoming,dc['edges'],dc['mask'],dc['request'],dc['relations']);mx.eval(first,source_tokens,logits,tokens)
    seen=set();selected=[]
    for record in transfers:
        i=record['chain'];pair=(int(chain['producer'][i]),int(chain['consumer'][i]))
        if pair not in seen:seen.add(pair);selected.append(record)
    available=len(selected);selected=selected[:a.limit];reports=[]
    for record in selected:
        i=record['chain'];local,host,cp,ctx,tp,src,dst,seed_count,oracle=initial_case(recipe,record)
        state=device(host);state['tokens']=state['tokens'].at[src].add(source_tokens[i]);state['tokens']=state['tokens'].at[dst].add(tokens[i])
        admitted=(first[i]>=0)&(logits[i]>=0)&mx.all(mx.isfinite(tokens[i]))
        state['active']=state['active']&admitted
        plan=device(cp);registry=device(ctx);next_id=mx.array(seed_count);settled=mx.array(True)
        # Fixed bounded device completion passes; no CPU RHS values enter here.
        executed=mx.array(0);created=mx.array(0);merged=mx.array(0)
        for _ in range(2):
            state,next_id,marks=complete(state,plan,next_id,mx.array(len(ctx['roots'])),mx.array(64),mx.array(True),settled,mx,registry,eq_rounds=8)
            registry=marks['eq_context'];settled=marks['eq_settled'];executed+=marks['executed'];created+=marks['new_constructors'];merged+=marks['new_equivalences']
        before=state
        if tp['covered']:
            state,move=handoff(state,device(tp),mx.array(src),mx.array(dst),mx.array(1),mx.array(1),logits[i],tokens[i],~marks['needs_attention']&(first[i]>=0),mx.array(True),mx)
        else:move=dict(transferred=mx.array(False),copied_fields=mx.array(0))
        mx.eval(state,next_id,marks,move,executed,created,merged)
        final={k:np.array(v) for k,v in state.items()};facts,covered=facts_from_cells(local,final)
        check=compare_graph(oracle,facts,np.array(registry['roots'])[:int(next_id)],seed_count)
        preserved=True;rr=np.arange(len(host['present']))[:,None];ss=np.arange(host['owner_projection'].shape[1])[None,:]
        before_host={k:np.array(v) for k,v in before.items()}
        for column in COLUMNS:
            if 'owner_'+column in final:preserved &= np.array_equal(read(before_host,column,rr,ss,np),read(final,column,rr,ss,np))
        report=dict(producer=int(chain['producer'][i]),consumer=int(chain['consumer'][i]),executed=int(executed),new_constructors=int(created),new_equivalences=int(merged),pending=bool(marks['needs_attention']),graph=check,facts_decoded=covered,transfer_covered=tp['covered'],transferred=bool(move['transferred']),copied_fields=int(move['copied_fields']),interfaces_preserved=bool(preserved),token_retained=bool(np.array_equal(np.array(state['tokens'][dst]),np.array(tokens[i]))))
        reports.append(report);print(json.dumps(report),flush=True)
    result=dict(scope='GPU exact RHS completion and neural-token owner transfer on independent synthetic initial snapshots; not autonomous matching or saturation',cases=reports,available_template_pairs=available,selected_pairs=len(reports),weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),cpu_prefilled_target_rhs=False,cpu_supplied_initial_bindings=True,wall_seconds=time.perf_counter()-started,speedup_claim=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    if any(r['pending'] or not r['graph']['passed'] or not r['facts_decoded'] or not r['interfaces_preserved'] or not r['token_retained'] for r in reports):raise SystemExit(1)


if __name__=='__main__':main()
