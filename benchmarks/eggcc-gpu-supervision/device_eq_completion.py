"""Bounded device Eq/congruence closure over resident Cell witnesses.

This exact correctness path uses dense comparisons, not a fast learned completion
model. Stable identities stay in slots; only slot_roots is refreshed. A round
budget is never interpreted as saturation.
"""
from device_witness_views import project
from device_slot_owners import shape,read,has,live


def merge_round(roots,sorts,pairs,active,xp):
    size=roots.shape[0]
    if size<1 or pairs.shape[0]<1:raise ValueError('positive static capacities required')
    safe=xp.clip(pairs,0,size-1)
    in_range=xp.all((pairs>=0)&(pairs<size),axis=1)
    typed=(sorts[safe[:,0]]==sorts[safe[:,1]])&(sorts[safe[:,0]]>=0)
    root_valid=xp.all((roots>=0)&(roots<size)&(roots<=xp.arange(size)))
    safe_roots=xp.clip(roots,0,size-1)
    root_valid=root_valid & xp.all(sorts==sorts[safe_roots])
    allowed=active&in_range&typed&root_valid
    ends=safe_roots[safe];small=xp.minimum(ends[:,0],ends[:,1])
    labels=xp.arange(size,dtype=roots.dtype)
    # Each accepted pair contributes its minimum to its two root addresses.
    # Scatter is equivalent to dense identity-by-pair reduction without that
    # O(identity capacity * pair capacity) temporary.
    values=xp.where(allowed,small,size)
    if xp.__name__=='numpy':
        mapping=labels.copy()
        xp.minimum.at(mapping,ends[:,0],values)
        xp.minimum.at(mapping,ends[:,1],values)
    else:
        mapping=labels.at[ends[:,0]].minimum(values).at[ends[:,1]].minimum(values)
    updated=mapping[safe_roots];updated=updated[updated]
    # Invalid starting partitions cannot authorize any output roots.
    updated=xp.where(root_valid,updated,roots)
    return updated, xp.any(active&~(in_range&typed)) | ~root_valid


def refresh_slots(state,roots,eq_slots,xp):
    size=roots.shape[0];output=dict(state)
    if 'slot_owner' in state:
        import numpy as np
        n,width=shape(state);rows=xp.arange(n)[:,None];slots=xp.arange(width)[None,:]
        owners=state['owner_slots'].shape[0]
        used=state['present'][:,None]&read(state,'slot_valid',rows,slots,xp)
        address=xp.clip(state['slot_owner'],0,owners-1)[:,None]*width+xp.clip(state['owner_projection'],0,width-1)
        def count(mask):
            if xp is np:return np.bincount(address.reshape(-1),weights=mask.reshape(-1),minlength=owners*width).reshape(owners,width)
            return xp.zeros(owners*width,xp.int32).at[address.reshape(-1)].add(mask.reshape(-1).astype(xp.int32)).reshape(owners,width)
        eq=count(used&eq_slots)>0;scalar=count(used&~eq_slots)>0
        ids=state['owner_slots'];valid=(ids>=0)&(ids<size)
        conflict=xp.any(eq&scalar)
        before=read(state,'slot_roots' if has(state,'slot_roots') else 'slots',rows,slots,xp)
        old=state.get('owner_slot_roots',ids)
        updated=xp.where(eq&valid,roots[xp.clip(ids,0,size-1)],old)
        output['owner_slot_roots']=xp.where(conflict,old,updated)
        after=read(output,'slot_roots',rows,slots,xp)
        changed=xp.any(used&eq_slots&(before!=after),axis=1)
        invalid=xp.any(eq&~valid)|conflict|xp.any(state['present']&~live(state,xp.arange(n),xp))
    else:
        ids=state['slots'];used=state['present'][:,None]&state['slot_valid']&eq_slots
        valid=(ids>=0)&(ids<size)
        output['slot_roots']=xp.where(used&valid,roots[xp.clip(ids,0,size-1)],ids)
        changed=xp.any(used & (output['slot_roots']!=state.get('slot_roots',ids)),axis=1)
        invalid=xp.any(used&~valid)
    output['token_dirty']=state.get('token_dirty',xp.zeros_like(changed)) | changed
    return output,invalid


def close(state,roots,sorts,eq_slots,pairs,active,views,external_complete,rounds,xp):
    if rounds<1:raise ValueError('positive round budget required')
    external_complete=xp.array(external_complete,dtype=xp.bool_)
    invalid_checks=[];missing_checks=[];changed=xp.array(True)
    for _ in range(rounds):
        before=roots
        roots,bad=merge_round(roots,sorts,pairs,active,xp);invalid_checks.append(bad)
        current,bad=refresh_slots(state,roots,eq_slots,xp);invalid_checks.append(bad)
        pending_pairs=[pairs];pending_masks=[active]
        for plan in views:  # Static Bake plans; no host reads of device state.
            # Provisional labels generate conditions only, never settlement.
            witness=project(current,plan,external_complete,xp.array(True),xp)
            missing_checks.append(~witness['complete'])
            n=witness['ids'].shape[0];ix=xp.arange(n)
            same=xp.all(witness['keys'][:,None,:]==witness['keys'][None,:,:],axis=2)
            condition=(same&witness['live'][:,None]&witness['live'][None,:]
                       &(ix[:,None]<ix[None,:]))
            left=xp.broadcast_to(witness['ids'][:,None],(n,n))
            right=xp.broadcast_to(witness['ids'][None,:],(n,n))
            pending_pairs.append(xp.stack([left,right],axis=2).reshape(-1,2))
            pending_masks.append(condition.reshape(-1))
        roots,bad=merge_round(roots,sorts,xp.concatenate(pending_pairs,axis=0),xp.concatenate(pending_masks),xp)
        invalid_checks.append(bad);changed=xp.any(roots!=before)
    output,bad=refresh_slots(state,roots,eq_slots,xp);invalid_checks.append(bad)
    invalid=xp.any(xp.stack(invalid_checks))
    missing=xp.any(xp.stack(missing_checks)) if missing_checks else xp.array(False)
    pending=changed|invalid|missing|~external_complete
    return output,roots,dict(settled=~pending,budget_pending=changed,invalid=invalid,missing_view=missing,needs_attention=pending,token_refresh_required=xp.any(output['token_dirty']))


def compile_unions(recipe):
    import numpy as np
    sites=[];marks=[]
    for rid,r in enumerate(recipe['rules']):
        for oi,op in enumerate(r['effects']):
            if op['kind']!='union':continue
            if len(op['args'])!=2 or any('slot' not in a for a in op['args']):
                marks.append(dict(rule=rid,operation=oi,reason='non_slot_union'));continue
            left,right=[a['slot'] for a in op['args']]
            if r['slots'][left]['sort']!=r['slots'][right]['sort'] or r['slots'][left]['sort']['kind']!='eq':
                raise ValueError('union must have one Eq sort')
            sites.append(dict(rule=rid,operation=oi,left=left,right=right,last=oi==len(r['effects'])-1))
    if not sites:sites=[dict(rule=-1,operation=-1,left=0,right=0,last=False)]
    return {k:np.array([s[k] for s in sites],bool if k=='last' else np.int32) for k in sites[0]},marks


def union_inputs(state,plan,xp):
    selected=(state['present'][:,None]&state['active'][:,None]&state['visible'][:,None]&~state['settled'][:,None]
              &(state['keys'][:,0,None]==plan['rule'][None,:])&(state['effect_pc'][:,None]==plan['operation'][None,:]))
    rows=xp.arange(shape(state)[0])[:,None]
    available=read(state,'slot_valid',rows,plan['left'][None,:],xp)&read(state,'slot_valid',rows,plan['right'][None,:],xp)
    pairs=xp.stack([read(state,'slots',rows,plan['left'][None,:],xp),read(state,'slots',rows,plan['right'][None,:],xp)],axis=2)
    return pairs.reshape(-1,2),(selected&available).reshape(-1),selected&~available


def finish_unions(state,plan,active,closure,xp):
    # Source snapshot is unchanged between collection and this ordered finish.
    accepted=active.reshape(shape(state)[0],-1)&closure['settled']
    advance=xp.any(accepted,axis=1)
    output=dict(state)
    output['effect_pc']=state['effect_pc']+advance.astype(xp.int32)
    output['settled']=state['settled']|xp.any(accepted&plan['last'][None,:],axis=1)
    return output,advance


def main():
    import argparse,hashlib,json
    from pathlib import Path
    from collect_observed_corpus import read_bytes
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.source);recipe=json.loads(raw)['recipe'];plan,marks=compile_unions(recipe)
    result=dict(source_sha256=hashlib.sha256(raw).hexdigest(),compiled_union_sites=int((plan['rule']>=0).sum()),
        unsupported_union_sites=marks,scope='Static union-site lowering only; no workload executed',
        global_identity_registry_required=True,complete_witness_views_required=True,
        bounded_rounds_do_not_prove_saturation=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
