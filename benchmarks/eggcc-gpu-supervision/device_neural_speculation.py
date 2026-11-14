"""Isolated speculative Cell frames: neural Eq changes actual query-visible roots.

Template wiring creates slots and fresh stable handles. No exact RHS union or
congruence repair runs here. The caller must audit before accepting the snapshot;
completion of this frame is not a saturation certificate.
"""
import numpy as np
from device_slot_owners import COLUMNS,read,shape
from device_token_commit import commit


def compile_frame(rule,width,eq_width,recipe=None,reuse_witnesses=False):
    from typed_literal import compiled_id
    def operand(a):
        return "slot" in a or (recipe is not None and compiled_id(a,recipe)>=0)
    if len(rule['slots'])>min(width,eq_width):raise ValueError('semantic layout exceeds frame')
    operations=[]
    for op in rule['effects']:
        if op['kind']=='copy' and 'slot' in op['arg']:operations.append(('copy',op['dst'],op['arg']['slot']))
        elif op['kind']=='construct' and all(operand(a) for a in op['args']) and op['sort']['kind']=='eq':operations.append(('fresh',op['dst'],0))
        elif op['kind']=='union' and all('slot' in a for a in op['args']):continue
        elif op['kind']=='set' and 'slot' in op['value'] and all('slot' in a for a in op['args']):continue
        else:raise ValueError('unbaked speculative effect')
    indices=np.zeros((width,width),np.int32);allowed=np.zeros((width,width),bool)
    for k,(i,j) in enumerate(zip(*np.triu_indices(eq_width,1))):
        if j>=len(rule['slots']):continue
        si,sj=rule['slots'][i]['sort'],rule['slots'][j]['sort']
        indices[i,j]=indices[j,i]=k
        allowed[i,j]=allowed[j,i]=si['kind']=='eq' and si==sj
    import json
    from multi_entry_ridge import scalar
    constants=[(i,json.loads(k)) for k,i in (recipe or {}).get('literal_ids',{}).items()]
    constants=[(i,v) for i,v in constants if v['sort']=='i64']
    from device_source_witness import compile_sites
    witness_sites=compile_sites(recipe,rule) if reuse_witnesses else {}
    return dict(witness_sites=witness_sites,literal_inputs=[s['sort'].get('kind')=='i64' and s['sort'].get('name')=='i64' for s in rule['slots']],literal_ids=np.array([i for i,v in constants],np.int32),literal_codes=np.array([scalar(v) for i,v in constants],np.float32).reshape(-1,64),literal_numbers=np.array([v['value'] for i,v in constants],np.float32),operations=operations,inputs=[s for s,d in enumerate(rule['slots']) if d['definition']=='query'],pair_index=indices,allowed=allowed,slots=len(rule['slots']))


def frame_payload(state,plan,batch,index,scores,fresh_base,roots,xp):
    _,width=shape(state);payload={}
    for column in COLUMNS:
        old=state['owner_'+column] if 'slot_owner' in state else state[column]
        payload[column]=xp.full((1,)+old.shape[1:],-1 if column in ('slots','slot_roots') else 0,old.dtype)
    for k,slot in enumerate(plan['inputs']):
        address=batch['binding_slots'][index,k]
        constant=address<0
        literal_live=xp.array(False);literal_index=xp.array(0)
        if len(plan.get('literal_ids',[])):
            matches=xp.array(plan['literal_ids'])==batch['binding_roots'][index,k]
            literal_live=xp.any(matches)&plan['literal_inputs'][slot];literal_index=xp.argmax(matches.astype(xp.int32))
        for column in COLUMNS:
            value=read(state,column,batch['binding_sources'][index,k],xp.maximum(address,0),xp)
            if len(plan.get('literal_ids',[])):
                if column in ('slots','slot_roots'):literal=batch['binding_roots'][index,k]
                elif column in ('slot_valid','scalar_valid','scalar_numeric'):literal=literal_live
                elif column=='scalar_codes':literal=xp.array(plan['literal_codes'])[literal_index]
                elif column=='scalar_numbers':literal=xp.array(plan['literal_numbers'])[literal_index]
                else:raise ValueError('unsupported literal column')
                value=xp.where(constant,literal,value)
            elif column in ('slot_valid','scalar_valid'):value=value&~constant
            mask=xp.arange(width)==slot
            payload[column]=xp.where(mask[None,:,None] if column=='scalar_codes' else mask[None,:],value,payload[column])
    for kind,dst,src in plan['operations']:
        mask=(xp.arange(width)==dst)[None,:]
        if kind=='fresh':
            identity=root=fresh_base+dst
            if dst in plan['witness_sites']:
                from device_source_witness import lookup
                found,witness,witness_root=lookup(state,payload,batch,index,plan['witness_sites'][dst],xp)
                identity=xp.where(found,witness,identity);root=xp.where(found,witness_root,root)
            for column,value in (('slots',identity),('slot_roots',root)):payload[column]=xp.where(mask,value,payload[column])
            payload['slot_valid']=payload['slot_valid']|mask
        else:
            for column in COLUMNS:
                payload[column]=xp.where(mask[:,:,None] if column=='scalar_codes' else mask,payload[column][:,src:src+1],payload[column])
    before=payload['slot_roots'][0];valid=payload['slot_valid'][0]
    allowed=xp.array(plan['allowed'])&valid[:,None]&valid[None,:]
    adjacency=allowed&((scores[xp.array(plan['pair_index'])]>=0)|(before[:,None]==before[None,:]))
    adjacency=adjacency|xp.eye(width,dtype=xp.bool_)
    labels=before
    for _ in range(width):labels=xp.min(xp.where(adjacency,labels[None,:],xp.iinfo(labels.dtype).max),axis=1)
    # Preserve the base snapshot's exact identities; the overlay aliases their
    # current roots and the new frame's handles without rewriting stable slots.
    handles=xp.arange(len(roots))
    allocated=xp.any((handles[:,None]==before[None,:])&valid[None,:],axis=1)
    # Earlier speculative frames collapse unused capacity to root zero. A
    # newly allocated handle must regain its own identity before aliasing.
    roots=xp.where(allocated&(handles>=fresh_base),handles,roots)
    live=(handles<fresh_base)|allocated
    roots=xp.where(live,roots,roots[0])
    alias=xp.where((roots[:,None]==before[None,:])&valid[None,:],labels[None,:],roots[:,None])
    proposed=xp.min(alias,axis=1)
    payload['slot_roots']=proposed[xp.clip(before,0,len(roots)-1)][None,:]
    ready=xp.all(valid[:plan['slots']])&xp.all(xp.isfinite(scores))&(fresh_base>=0)&(fresh_base<=len(roots)-width)
    return payload,proposed,ready


def install(state,payload,roots,batch,index,token,rule_id,inputs,ready,xp,dirty=False):
    kw=state['keys'].shape[1]
    if len(inputs)+1>kw:raise ValueError('key capacity')
    keys=xp.concatenate([xp.array([[rule_id]],xp.int32),batch['binding_roots'][index][None,:],xp.full((1,kw-len(inputs)-1),-1,xp.int32)],axis=1)
    p=dict(payload,keys=keys,tokens=token[None,:],matched=ready[None],completed=xp.ones(1,xp.bool_),source=xp.array([-1],xp.int32),generation=xp.array([0],xp.int32),transfer_covered=xp.zeros(1,xp.bool_),witness_sources=batch['sources'][index][None,:],witness_valid=batch['mask'][index][None,:],witness_generations=batch['generations'][index][None,:])
    out,marks=commit(state,p,xp)
    from device_witness_context import retain
    out=retain(state,out,batch,index,xp)
    accepted=xp.any(marks['accepted']);changed=out['present']&~state['present']
    if 'slot_owner' in out:
        old=out['owner_slot_roots'];out['owner_slot_roots']=xp.where(accepted&out['owner_slot_valid'],roots[xp.clip(old,0,len(roots)-1)],old)
    else:
        old=out['slot_roots'];out['slot_roots']=xp.where(accepted&out['slot_valid'],roots[xp.clip(old,0,len(roots)-1)],old)
    n,width=shape(state);rr=xp.arange(n)[:,None];ss=xp.arange(width)[None,:]
    previous=read(state,'slot_roots',rr,ss,xp);valid=read(state,'slot_valid',rr,ss,xp)
    affected=state['present']&accepted&xp.any(valid&(previous!=roots[xp.clip(previous,0,len(roots)-1)]),axis=1)
    out['token_dirty']=out.get('token_dirty',xp.zeros_like(changed))|affected|(changed&dirty)
    return out,dict(marks,needs_attention=marks['needs_attention']|accepted|~ready,awaiting_audit=accepted,token_refresh_required=xp.any(affected|(changed&dirty)))


def resolve(current,predicted,corrected,audit_ok,audit_epoch,current_epoch,xp):
    """Atomic snapshot selection; a stale verdict cannot alter a newer fork."""
    current_verdict=audit_epoch==current_epoch
    chosen={k:xp.where(audit_ok,predicted[k],corrected[k]) for k in current}
    result={k:xp.where(current_verdict,chosen[k],current[k]) for k in current}
    return result,dict(stale_audit=~current_verdict,rolled_back=current_verdict&~audit_ok,awaiting_audit=~current_verdict)
