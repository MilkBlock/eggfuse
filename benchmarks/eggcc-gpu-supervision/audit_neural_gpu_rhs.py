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
from neural_ordered_relations import ordered_model
from lower_constructor_sets import lower
from device_snapshot_import import prepare_family,identity,eq_registry
from device_constructor_completion import compile_completion,complete
from device_slot_owners import pack,read,compile_transfer,COLUMNS
from neural_owner_handoff import handoff
from reference_union_family import Reference,compare_graph
from reference_cell_closure import facts_from_cells
from audit_snapshot_queries import device
from multi_entry_ridge import scalar


def initial_case(recipe,record,spare=0):
    oldplan=record['plan'];ref=record['initial_reference']
    original=dict(recipe,rules=[recipe['rules'][oldplan['producer']],recipe['rules'][oldplan['consumer']]])
    lowered,_=lower(original)
    def value(v):
        v=ref.root(v)
        return dict(sort=ref.types[v],eq=str(v)) if ref.types[v] is not None else ref.scalar_values[v]
    snapshot=dict(rows=[dict(table=t,values=[value(v) for v in vs],subsumed=False) for t,vs in sorted(ref.normalized_facts())])
    local,state,ids,rows=prepare_family(lowered,snapshot,[0,1],2+spare)
    full_lowered,_=lower(recipe);width=max(len(r['slots']) for r in full_lowered['rules'])
    if spare:
        kw=1+max(sum(s['definition']=='query' for s in r['slots']) for r in recipe['rules'])
        state['keys']=np.pad(state['keys'],((0,0),(0,max(0,kw-state['keys'].shape[1]))),constant_values=-1)
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
    p.add_argument('--speculate',action='store_true');p.add_argument('--context-capacity',type=int,default=0);p.add_argument('--interface-only',action='store_true');p.add_argument('--eq-readout',type=Path)
    p.add_argument('--limit',type=int,default=8);p.add_argument('--follow',action='store_true');a=p.parse_args()
    if a.limit<1:raise ValueError('positive case budget required')
    if a.speculate and not a.eq_readout:raise ValueError('speculation requires semantic readout')
    if a.eq_readout and not (a.follow and a.interface_only):raise ValueError('Eq audit requires interface-only following candidates')
    raw=json.loads(a.trace.read_text());source=raw.get('recipe',raw);recipe=dict(source,rules=[r for r in source['rules'] if r['metadata']['source_set']=='context'])
    started=time.perf_counter();records=[];base=samples(recipe,4,93003,records,ordered=True);transfers=[]
    chain,_=chains(recipe,records,ordered=True,transfers=transfers)
    model=ordered_model(base['x'].shape[-1],base['relations'].shape[-1],a.interface_only);model.load_weights(str(a.weights))
    eq_head=None
    if a.eq_readout:
        from neural_eq_readout import EqReadout
        eq_head=EqReadout(max(len(r['slots']) for r in recipe['rules']));eq_head.load_weights(str(a.eq_readout))
    parent=device({k:v[chain['parent']] for k,v in base.items()});dc=device(chain)
    first,source_tokens=model(parent['x'],parent['edges'],parent['mask'],parent['request'],parent['relations'])
    from train_neural_cell_chains import incoming_tokens
    incoming=incoming_tokens(model,dc,source_tokens)
    logits,tokens=model.transition(incoming,dc['edges'],dc['mask'],dc['request'],dc['relations']);mx.eval(first,source_tokens,logits,tokens)
    seen=set();selected=[]
    for record in transfers:
        i=record['chain'];pair=(int(chain['producer'][i]),int(chain['consumer'][i]))
        if pair not in seen:seen.add(pair);selected.append(record)
    available=len(selected);selected=selected[:a.limit];reports=[]
    for record in selected:
        i=record['chain'];local,host,cp,ctx,tp,src,dst,seed_count,oracle=initial_case(recipe,record,spare=int(a.speculate))
        if a.speculate:local=dict(local,rules=local['rules']+recipe['rules'])
        state=device(host);state['tokens']=state['tokens'].at[src].add(source_tokens[i]);state['tokens']=state['tokens'].at[dst].add(tokens[i])
        if a.follow:
            from neural_device_candidates import compile_frames,encode_seeds
            frames=device(compile_frames(local,host['owner_projection'].shape[1]))
            state=encode_seeds(state,frames,model,mx)
            cp['retain_predicted_rules']=tuple(range(len(local['rules'])))
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
        check=compare_graph(oracle,facts,np.array(registry['roots'])[:int(next_id)],seed_count,include_mapping=a.follow)
        preserved=True;rr=np.arange(len(host['present']))[:,None];ss=np.arange(host['owner_projection'].shape[1])[None,:]
        before_host={k:np.array(v) for k,v in before.items()}
        for column in COLUMNS:
            if 'owner_'+column in final:preserved &= np.array_equal(read(before_host,column,rr,ss,np),read(final,column,rr,ss,np))
        report=dict(producer=int(chain['producer'][i]),consumer=int(chain['consumer'][i]),executed=int(executed),new_constructors=int(created),new_equivalences=int(merged),pending=bool(marks['needs_attention']),graph=check,facts_decoded=covered,transfer_covered=tp['covered'],transferred=bool(move['transferred']),copied_fields=int(move['copied_fields']),interfaces_preserved=bool(preserved),token_retained=bool(np.array_equal(np.array(state['tokens'][dst]),np.array(tokens[i]))))
        if a.follow and check['passed']:
            report['follow']=follow_candidates(recipe,local,state,frames,model,oracle,check.pop('mapping'),dst,eq_head,a.context_capacity,(registry['roots'],int(next_id),seed_count) if a.speculate else None)
        reports.append(report);print(json.dumps(report),flush=True)
    result=dict(scope='GPU exact RHS completion and neural-token owner transfer on independent synthetic initial snapshots; not autonomous matching or saturation',cases=reports,available_template_pairs=available,selected_pairs=len(reports),recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest(),weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),interface_only=a.interface_only,cpu_prefilled_target_rhs=False,cpu_supplied_initial_bindings=True,device_follow_candidates=a.follow,context_capacity=a.context_capacity,speculative_frames=a.speculate,wall_seconds=time.perf_counter()-started,speedup_claim=False)
    if a.eq_readout:result['readout_weights_sha256']=hashlib.sha256(a.eq_readout.read_bytes()).hexdigest()
    failed=audit_failed(reports,a.follow,a.speculate)
    result['status']='difference' if failed else 'pass'
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    if failed:raise SystemExit(1)


def audit_failed(reports,follow=False,speculate=False):
    for r in reports:
        if r['pending'] or not r['graph']['passed'] or not r['facts_decoded'] or not r['interfaces_preserved'] or not r['token_retained']:return True
        if follow:
            if 'follow' not in r:return True
            c=r['follow']['counts']
            required=('false_positive','missed','incomplete_rules','invalid_predictions')
            if any(k not in c for k in required) or any(c[k] for k in required):return True
            if c.get('semantic_wrong_states',0):return True
        if speculate:
            s=r.get('follow',{}).get('speculation')
            required=('gpu_installed','corrected_graph_pass','token_refresh_required','downstream_false_positive','downstream_missed','downstream_incomplete')
            if not s or any(k not in s for k in required):return True
            if s['corrected_graph_pass']!=s['gpu_installed'] or any(s[k] for k in required[2:]):return True
    return not reports


def follow_candidates(recipe,local,state,frames,model,oracle,mapping,generated_row,eq_head=None,context_capacity=0,speculation=None):
    from neural_device_candidates import compile_candidates,candidates
    counts=dict(candidates=0,accepted=0,false_positive=0,expected=0,recovered=0,missed=0,incomplete_rules=0,accepted_from_generated=0,invalid_predictions=0,context_overflow_rules=0,context_inputs=0)
    groups=[];spec_reports=[]
    if speculation is not None:
        from neural_speculation_audit import audit as audit_speculation
    if eq_head is not None:
        from copy import deepcopy
        from neural_cell_samples import apply_instance
        from neural_cell_chains import completed
        from neural_eq_readout import targets,metrics
        width=max(len(r['slots']) for r in recipe['rules'])
        counts.update(semantic_states=0,semantic_wrong_states=0,semantic_false_merge_states=0,semantic_local_wrong_states=0,semantic_external_eq_states=0,semantic_feature_conflicts=0,semantic_local_feature_conflicts=0)
    for rid,rule in enumerate(recipe['rules']):
        host_plan=compile_candidates(local,rule,context_capacity=context_capacity)
        batch=candidates(state,frames,device(host_plan),mx.array(True),mx.array(True),mx)
        logits,tokens=model.transition(batch['tokens'],batch['edges'],batch['mask'],batch['request'],batch['relations']);mx.eval(batch,logits,tokens)
        if eq_head is not None:
            semantic=eq_head(tokens,batch['request']);mx.eval(semantic)
            eq_scores=[];eq_labels=[];eq_masks=[];eq_local=[];feature_labels={};conflicts=local_conflicts=0
            features={k:np.array(batch[k]) for k in ('tokens','edges','mask','request','relations')}
        live=np.array(batch['live']);finite=np.isfinite(np.array(logits))&np.isfinite(np.array(tokens)).all(axis=1);pred=(np.array(logits)>=0)&live&finite
        roots=np.array(batch['binding_roots']);sources=np.array(batch['sources'])
        relations=np.array(batch['relations']);half=relations.shape[1]//2
        valid=np.all((relations[:,half:]==0)|(relations[:,:half]>0),axis=1)
        expected={tuple(sorted(b.items())) for b in oracle.matches(rule)};recovered=set();fp=0;from_generated=0
        for index in np.flatnonzero(pred):
            key=tuple((slot,mapping.get(int(root),-1)) for slot,root in zip(host_plan['inputs'],roots[index]))
            if not valid[index] or key not in expected:fp+=1;continue
            recovered.add(key)
            if eq_head is not None:
                ref=deepcopy(oracle);bound=dict(key);apply_instance(ref,rule,bound)
                truth=targets(rule,completed(rule,bound,ref),ref,width)
                eq_scores.append(np.array(semantic[index]));eq_labels.append(truth['eq_target']);eq_masks.append(truth['eq_mask'])
                local_ref=deepcopy(oracle);local_bound=dict(key)
                local_ref.facts=[(atom['call']['table'],tuple(local_bound[a['slot']] for a in atom['args'])) for atom in rule['query']]
                apply_instance(local_ref,rule,local_bound)
                eq_local.append(targets(rule,completed(rule,local_bound,local_ref),local_ref,width)['eq_target'])
                if speculation is not None:
                    spec_reports.append(audit_speculation(state,local,frames,rule,len(local['rules'])-len(recipe['rules'])+rid,batch,index,tokens[index],semantic[index],model,oracle,key,mapping,*speculation,width))
                signature=hashlib.sha256(b''.join(features[k][index].tobytes() for k in features)).digest()
                value=(eq_labels[-1].tobytes(),eq_local[-1].tobytes())
                if signature in feature_labels:
                    conflicts+=value[0]!=feature_labels[signature][0];local_conflicts+=value[1]!=feature_labels[signature][1]
                else:feature_labels[signature]=value
            from_generated+=bool((sources[index,:host_plan['atoms']]==generated_row).any())
        group=dict(rule=rid,context_overflow_rules=int(bool(batch['context_overflow'])),context_inputs=int(np.array(batch['mask'])[pred,host_plan['atoms']:].sum()),invalid_predictions=int((live&~finite).sum()),candidates=int(live.sum()),accepted=int(pred.sum()),false_positive=fp,expected=len(expected),recovered=len(recovered),missed=len(expected-recovered),incomplete_rules=int(not bool(batch['complete'])),accepted_from_generated=from_generated)
        if eq_head is not None:
            m=metrics(np.array(eq_scores).reshape(-1,width*(width-1)//2),np.array(eq_labels).reshape(-1,width*(width-1)//2),np.array(eq_masks).reshape(-1,width*(width-1)//2),width)
            loc=np.array(eq_local).reshape(-1,width*(width-1)//2);full=np.array(eq_labels).reshape(loc.shape);mask=np.array(eq_masks,dtype=bool).reshape(loc.shape)
            lm=metrics(np.array(eq_scores).reshape(loc.shape),loc,mask,width)
            group.update(semantic_states=m['states'],semantic_wrong_states=m['states']-m['closed_exact_states'],semantic_false_merge_states=m['states_with_false_merge'],
                semantic_feature_conflicts=conflicts,semantic_local_feature_conflicts=local_conflicts,semantic_local_wrong_states=lm['states']-lm['closed_exact_states'],semantic_external_eq_states=int(((full>loc)&mask).any(axis=1).sum()))
        groups.append(group)
        for key,value in group.items():
            if key!='rule':counts[key]+=value
    return dict(counts=counts,groups=groups,cpu_supplied_follow_bindings=False,speculation={k:sum(r[k] for r in spec_reports) for k in spec_reports[0]} if spec_reports else None)


if __name__=='__main__':main()
