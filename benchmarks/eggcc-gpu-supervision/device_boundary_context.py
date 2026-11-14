"""Current boundary-neighbor messages, using sealed Cell payloads only.

Static roles are baked. IDs provide typed connectivity, never float embeddings.
This is an experimental encoder, not evidence permitting a rule or takeover.
"""
import numpy as np
from device_semantic_template import semantic, template
from device_slot_owners import shape, read, live


def compile_context(recipe, rid, width, hidden=32):
    names=sorted({s['sort']['name'] for r in recipe['rules'] for s in r['slots'] if s['sort']['kind']=='eq'})
    roles=np.zeros((len(recipe['rules']),width,64),np.float32)
    sorts=np.full((len(recipe['rules']),width),-1,np.int32)
    for i,raw in enumerate(recipe['rules']):
        r,_=semantic(raw);rr,_=template(r)
        if len(r['slots'])>width:raise ValueError('context width')
        roles[i,:len(rr)]=rr
        for j,s in enumerate(r['slots']):
            if s['sort']['kind']=='eq':sorts[i,j]=names.index(s['sort']['name'])
    r,_=semantic(recipe['rules'][rid]);ports=[i for i,s in enumerate(r['slots']) if s['definition']=='query' and s['sort']['kind']=='eq']
    used={op.get('call',{}).get('table') for rule in recipe['rules'] for op in [*rule['query'],*rule['effects']]}
    outputs={t['schema'][-1]['name'] for t in recipe.get('tables',[]) if t['name'] in used and t['kind']=='constructor' and t.get('schema') and t['schema'][-1]['kind']=='eq'}
    flow_sorts=np.array([name in outputs for name in names],bool)
    rng=np.random.default_rng(20261116)
    return dict(flow_sorts=flow_sorts,roles=roles,sorts=sorts,ports=np.array(ports,np.int32),
        port_sorts=sorts[rid,ports],width=width,
        token_weight=rng.normal(0,1/np.sqrt(128),(128,hidden)).astype(np.float32),
        role_weight=rng.normal(0,1/8,(64,hidden)).astype(np.float32))


def snapshot(state,xp):
    n,w=shape(state);rows=xp.arange(n)
    out={k:read(state,k,rows[:,None],xp.arange(w)[None,:],xp) for k in ('slots','slot_roots','slot_valid')}
    out.update(rule=state['keys'][:,0],tokens=state['tokens'],generation=state['generation'])
    out['live']=state['present']&state['visible']&state['settled']&~state['token_dirty']&live(state,rows,xp)
    return out


def prepare(boundary,plan,xp):
    sr=boundary['rule'];safe=xp.clip(sr,0,plan['sorts'].shape[0]-1)
    valid=boundary['live'][:,None]&boundary['slot_valid']&(sr[:,None]>=0)&(sr[:,None]<plan['sorts'].shape[0])
    valid=valid&(plan['sorts'][safe]>=0)
    tokens=xp.where(boundary['live'][:,None],boundary['tokens'],0)
    h=xp.tanh((tokens@plan['token_weight'])[:,None,:]+plan['roles'][safe]@plan['role_weight'])
    return dict(safe=safe,valid=valid,messages=xp.where(valid[:,:,None],h,0))


def masks(boundary,bindings,plan,xp):
    sr=boundary['rule'];safe=xp.clip(sr,0,plan['sorts'].shape[0]-1)
    valid=boundary['live'][:,None]&boundary['slot_valid']&(sr[:,None]>=0)&(sr[:,None]<plan['sorts'].shape[0])
    sorts=plan['sorts'][safe];valid=valid&(sorts>=0)
    ports=plan['ports'];roots=bindings['slot_roots'][:,ports]
    selected=xp.any(bindings['witness_rows'][:,:,None]==xp.arange(len(sr))[None,None,:],axis=1)
    conn=(roots[:,:,None,None]==boundary['slot_roots'][None,None,:,:])&(plan['port_sorts'][None,:,None,None]==sorts[None,None,:,:])
    conn=conn&valid[None,None,:,:]&bindings['live'][:,None,None,None]&bindings['slot_valid'][:,ports,None,None]
    return conn,conn&~selected[:,None,:,None],safe,valid


def encode(boundary,bindings,plan,xp,prepared=None):
    all_mask,other_mask,safe,valid=masks(boundary,bindings,plan,xp)
    prepared=prepare(boundary,plan,xp) if prepared is None else prepared
    h=prepared['messages'];h=h.reshape(-1,h.shape[-1])
    outputs=[];counts=[]
    for mask in (all_mask,other_mask):
        count=xp.sum(mask.astype(xp.float32),axis=(-2,-1))
        pooled=mask.reshape(mask.shape[0],mask.shape[1],-1).astype(xp.float32)@h
        pooled=xp.tanh(pooled/xp.sqrt(xp.maximum(count,1))[:,:,None])
        # Preserve port position with a shared padded family layout.
        slots=xp.arange(plan['width'])[:,None]==plan['ports'][None,:]
        outputs.append((slots.astype(xp.float32)[None,:,:]@pooled).reshape(mask.shape[0],-1))
        counts.append(count)
    return xp.concatenate(outputs,axis=1),xp.stack(counts,axis=1)
