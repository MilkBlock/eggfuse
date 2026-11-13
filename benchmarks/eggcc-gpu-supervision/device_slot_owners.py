"""Physical slot owners distinct from logical Cell identities.

Opt-in sealed-payload prototype. Logical keys/tokens/lifetimes remain authoritative;
no second dense copy of logical slots is retained. Constructor/copy writes detach
shared payloads; general completion and stage control still require integration.
"""
import numpy as np

COLUMNS=('slots','slot_roots','slot_valid','scalar_numbers','scalar_numeric','scalar_codes','scalar_valid')


def pack(state):
    n,width=state['slots'].shape
    out={k:v for k,v in state.items() if k not in COLUMNS}
    out.update({'owner_'+k:state[k] for k in COLUMNS if k in state})
    out.update(slot_owner=np.arange(n,dtype=np.int32),owner_epoch=np.ones(n,np.int32),
        owner_generation=np.ones(n,np.int32),owner_live=state['present'].copy(),
        owner_projection=np.where(state['slot_valid'],np.arange(width,dtype=np.int32)[None,:],-1))
    return out


def shape(state):
    return state['owner_projection'].shape if 'slot_owner' in state else state['slots'].shape


def dtype(state):return state['owner_slots'].dtype if 'slot_owner' in state else state['slots'].dtype


def has(state,column):return ('owner_'+column in state) if 'slot_owner' in state else column in state


def read(state,column,rows,slots,xp):
    if 'slot_owner' not in state:return state[column][rows,slots]
    owner=state['slot_owner'][rows];safe=xp.clip(owner,0,len(state['owner_live'])-1)
    projection=state['owner_projection'][rows,slots];p=xp.clip(projection,0,state['owner_slots'].shape[1]-1)
    valid=(owner>=0)&(owner<len(state['owner_live']))&state['owner_live'][safe]&(state['owner_epoch'][rows]==state['owner_generation'][safe])&(projection>=0)&(projection<state['owner_slots'].shape[1])
    data=state['owner_'+column][safe,p]
    mask=valid[...,None] if data.ndim>valid.ndim else valid
    return xp.where(mask,data,False if column in ('slot_valid','scalar_valid','scalar_numeric') else 0)


def live(state,rows,xp):
    if 'slot_owner' not in state:return xp.ones_like(rows,dtype=xp.bool_)
    owner=state['slot_owner'][rows];safe=xp.clip(owner,0,len(state['owner_live'])-1)
    return (owner>=0)&(owner<len(state['owner_live']))&state['owner_live'][safe]&(state['owner_epoch'][rows]==state['owner_generation'][safe])


def free_rows(state,xp):
    ids=xp.arange(len(state['owner_live']))
    referenced=xp.any(state['present'][:,None]&(state['slot_owner'][:,None]==ids[None,:]),axis=0)
    return ~state['owner_live']&~referenced&(state['owner_generation']<2147483647)


def allocate(state,proposals,accepted,rank,logical_write,pick,xp):
    """Allocate physical rows only for already admitted logical instances."""
    free=free_rows(state,xp);free_rank=xp.cumsum(free.astype(xp.int32))-1
    write=accepted[:,None]&free[None,:]&(rank[:,None]==free_rank[None,:])
    written=xp.any(write,axis=0);owner_pick=xp.argmax(write.astype(xp.int32),axis=0)
    destination=xp.argmax(write.astype(xp.int32),axis=1)
    out=dict(state)
    for column in COLUMNS:
        if not has(state,column):continue
        if column not in proposals:raise ValueError('proposal lost owner column: '+column)
        values=proposals[column]
        if values.shape[1:]!=state['owner_'+column].shape[1:]:raise ValueError('owner payload layout mismatch')
        mask=written[:,None,None] if values.ndim==3 else written[:,None]
        out['owner_'+column]=xp.where(mask,values[owner_pick],state['owner_'+column])
    out['owner_live']=state['owner_live']|written
    out['owner_generation']=state['owner_generation']+written.astype(xp.int32)
    out['slot_owner']=xp.where(logical_write,destination[pick],state['slot_owner'])
    out['owner_epoch']=xp.where(logical_write,out['owner_generation'][destination[pick]],state['owner_epoch'])
    width=state['owner_projection'].shape[1]
    projection=xp.where(proposals['slot_valid'][pick],xp.arange(width)[None,:],-1)
    out['owner_projection']=xp.where(logical_write[:,None],projection,state['owner_projection'])
    return out


def prepare_write(state,selected,xp):
    """Reserve possible detachments; do not mutate or consume capacity yet."""
    if 'slot_owner' not in state:return dict(ready=selected,blocked=xp.zeros_like(selected))
    n,width=shape(state);owners=len(state['owner_live']);rows=xp.arange(n)
    safe=xp.clip(state['slot_owner'],0,owners-1)
    references=xp.sum((state['present'][:,None]&(state['slot_owner'][:,None]==xp.arange(owners)[None,:])).astype(xp.int32),axis=0)
    identity=xp.all((state['owner_projection']<0)|(state['owner_projection']==xp.arange(width)[None,:]),axis=1)
    alive=live(state,rows,xp)
    private=alive&(references[safe]==1)&identity
    borrowed=state.get('readers',xp.zeros(n,xp.bool_))
    needs=selected&alive&~private&~borrowed&(state['owner_generation'][safe]<2147483647)
    rank=xp.cumsum(needs.astype(xp.int32))-1;free=free_rows(state,xp)
    free_rank=xp.cumsum(free.astype(xp.int32))-1
    place=needs[:,None]&free[None,:]&(rank[:,None]==free_rank[None,:])
    copy=needs&xp.any(place,axis=1)
    destination=xp.where(copy,xp.argmax(place.astype(xp.int32),axis=1),safe)
    ready=selected&alive&~borrowed&(private|copy)
    return dict(ready=ready,blocked=selected&~ready,copy=copy,destination=destination)


def write_slot(state,dst,values,commit,xp,plan):
    """One effect's authoritative writes, detaching shared payloads atomically."""
    n,width=shape(state);out=dict(state)
    if 'slot_owner' not in state:
        mask=commit[:,None]&(xp.arange(width)[None,:]==dst)
        for column,value in values.items():
            if column not in state:continue
            out[column]=xp.where(mask[...,None] if value.ndim>1 else mask,value[:,None,...],state[column])
        return out
    owners=len(state['owner_live']);commit=commit&plan['ready'];destination=plan['destination']
    assignment=commit[:,None]&(destination[:,None]==xp.arange(owners)[None,:])
    written=xp.any(assignment,axis=0);pick=xp.argmax(assignment.astype(xp.int32),axis=0)
    rows=xp.arange(n)[:,None];slots=xp.arange(width)[None,:]
    old=xp.clip(state['slot_owner'],0,owners-1)
    for column in COLUMNS:
        if not has(state,column):continue
        original=state['owner_'+column][old]
        logical=read(state,column,rows,slots,xp)
        cm=plan['copy'][:,None,None] if logical.ndim==3 else plan['copy'][:,None]
        data=xp.where(cm,logical,original)
        if column in values:
            m=slots==dst
            if data.ndim==3:m=m[...,None]
            data=xp.where(m,values[column][:,None,...],data)
        m=written[:,None,None] if data.ndim==3 else written[:,None]
        out['owner_'+column]=xp.where(m,data[pick],state['owner_'+column])
    copied=commit&plan['copy']
    allocated=xp.any(assignment&copied[:,None],axis=0)
    out['slot_owner']=xp.where(commit,destination,state['slot_owner'])
    retained=xp.any(state['present'][:,None]&(out['slot_owner'][:,None]==xp.arange(owners)[None,:]),axis=0)
    detached=xp.any(copied[:,None]&(state['slot_owner'][:,None]==xp.arange(owners)[None,:]),axis=0)
    freed=detached&~retained
    out['owner_live']=(state['owner_live']|allocated)&~freed
    out['owner_generation']=state['owner_generation']+(allocated|freed).astype(xp.int32)
    out['owner_epoch']=xp.where(commit,out['owner_generation'][destination],state['owner_epoch'])
    valid=read(state,'slot_valid',rows,slots,xp)|(slots==dst)
    projection=xp.where(valid,slots,-1)
    out['owner_projection']=xp.where(commit[:,None],projection,state['owner_projection'])
    return out


def ensure_roots(state,xp):
    out=dict(state,token_dirty=state.get('token_dirty',xp.zeros_like(state['present'])))
    if 'slot_owner' in state:out['owner_slot_roots']=state.get('owner_slot_roots',state['owner_slots'])
    else:out['slot_roots']=state.get('slot_roots',state['slots'])
    return out


def compile_transfer(recipe,entry,width):
    source=recipe['rules'][entry['producer']];target=recipe['rules'][entry['consumer']]
    if width<max(len(source['slots']),len(target['slots'])):raise ValueError('owner width too small')
    inputs=[i for i,s in enumerate(target['slots']) if s['definition']=='query']
    overwritten={o['dst'] for o in target['effects'] if 'dst' in o}
    mapping={}
    for slot,origin,valid in zip(inputs,entry['projection'],entry['projection_valid']):
        if valid and 0<=origin<len(source['slots']) and slot not in overwritten and target['slots'][slot]['sort']==source['slots'][origin]['sort']:mapping.setdefault(origin,slot)
    copied=[];next_slot=len(target['slots'])
    for slot in range(len(source['slots'])):
        if slot not in mapping:
            mapping[slot]=next_slot;next_slot+=1;copied.append(slot)
    if next_slot>width:return dict(covered=False,reason='combined_payload_capacity')
    return dict(covered=True,producer=entry['producer'],consumer=entry['consumer'],
                projection=np.array([mapping.get(i,0) for i in range(width)],np.int32),
                copied=np.array([i in copied for i in range(width)]),
                required=np.array([i<len(source['slots']) for i in range(width)]))



def transfer(state,plan,source,target,source_generation,target_generation,quiescent,xp):
    if not plan['covered']:raise ValueError('unproved slot takeover')
    n,width=shape(state);s=xp.clip(source,0,n-1);t=xp.clip(target,0,n-1)
    so=state['slot_owner'][s];to=state['slot_owner'][t];owners=len(state['owner_live'])
    safe_s=xp.clip(so,0,owners-1);safe_t=xp.clip(to,0,owners-1)
    logical=(source>=0)&(source<n)&(target>=0)&(target<n)&(source!=target)
    logical=logical&state['present'][s]&state['present'][t]&state['visible'][s]&state['visible'][t]&state['settled'][s]&state['settled'][t]
    logical=logical&(state['keys'][s,0]==plan['producer'])&(state['keys'][t,0]==plan['consumer'])&(state['generation'][s]==source_generation)&(state['generation'][t]==target_generation)
    owner_ok=(so>=0)&(so<owners)&(to>=0)&(to<owners)&(so!=to)&state['owner_live'][safe_s]&state['owner_live'][safe_t]&(state['owner_epoch'][s]==state['owner_generation'][safe_s])&(state['owner_epoch'][t]==state['owner_generation'][safe_t])
    slot=xp.arange(width);required=plan['required'];projection=plan['projection']
    equal=xp.array(True)
    for column in COLUMNS:
        if not has(state,column):continue
        a=read(state,column,s,slot,xp);b=read(state,column,t,projection,xp)
        same=(a==b)
        if same.ndim>1:same=xp.all(same,axis=-1)
        equal=equal&xp.all(~(required&~plan['copied'])|same)
    equal=equal&xp.all(~required|read(state,'slot_valid',s,slot,xp))
    # Map every old physical slot through the source's logical projection.
    old=state['owner_projection'][s];new=xp.where(plan['copied'],projection,state['owner_projection'][t,projection])
    spare=xp.all(~plan['copied']|~state['owner_slot_valid'][safe_t,projection])
    links=(slot[:,None]==old[None,:])&required[None,:]
    mapped=xp.any(links,axis=1);mapping=new[xp.argmax(links.astype(xp.int32),axis=1)]
    aliases=(state['slot_owner']==so)&state['present']
    all_refs=state['owner_projection'];safe_refs=xp.clip(all_refs,0,width-1)
    demanded=aliases[:,None]&state['owner_slot_valid'][safe_s,safe_refs]&(all_refs>=0)&(all_refs<width)
    covered=xp.all(~demanded|mapped[safe_refs])
    alias_epochs=xp.all(~aliases|(state['owner_epoch']==state['owner_generation'][safe_s]))
    epoch_ok=state['owner_generation'][safe_s]<2147483647
    ok=logical&owner_ok&equal&covered&alias_epochs&quiescent&spare&epoch_ok
    affected=aliases&ok
    out=dict(state)
    copy_links=(slot[:,None]==projection[None,:])&plan['copied'][None,:]
    copied=xp.any(copy_links,axis=1);pick=xp.argmax(copy_links.astype(xp.int32),axis=1)
    for column in COLUMNS:
        if not has(state,column):continue
        data=read(state,column,s,slot,xp)[pick]
        mask=(xp.arange(owners)[:,None]==to)&copied[None,:]&ok
        if data.ndim>1:mask=mask[...,None]
        out['owner_'+column]=xp.where(mask,data[None,...],state['owner_'+column])
    out['slot_owner']=xp.where(affected,to,state['slot_owner'])
    out['owner_epoch']=xp.where(affected,state['owner_generation'][safe_t],state['owner_epoch'])
    remapped=xp.where((all_refs>=0)&(all_refs<width)&mapped[safe_refs],mapping[safe_refs],-1)
    out['owner_projection']=xp.where(affected[:,None],remapped,all_refs)
    out['owner_live']=state['owner_live']&~((xp.arange(owners)==so)&ok)
    # Generation invalidates stale physical references before the row is reused.
    out['owner_generation']=state['owner_generation']+((xp.arange(owners)==so)&ok).astype(xp.int32)
    return out,dict(transferred=ok,released_rows=ok.astype(xp.int32),value_mismatch=~equal,
                    uncovered_alias=~covered,stale=~(logical&owner_ok&alias_epochs),waiting_readers=~xp.array(quiescent,dtype=xp.bool_),occupied_destination=~spare,epoch_exhausted=~epoch_ok,copied_fields=xp.sum(plan['copied'].astype(xp.int32))*ok)


def main():
    import argparse,json,hashlib
    from collections import Counter
    from pathlib import Path
    from collect_observed_corpus import read_bytes
    from cell_token_successors import compile_catalog
    from lower_device_entries import lower
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);recipe=json.loads(raw)['recipe']
    layout=lower(recipe,compile_catalog(recipe),source_slots=True)
    plans=[compile_transfer(recipe,e,layout['slot_width']) for e in layout['entries']]
    covered=[p for p in plans if p['covered']]
    result=dict(scope='recipe-only sealed-slot composition coverage; not executed storage savings',
        trace_sha256=hashlib.sha256(raw).hexdigest(),entries=len(plans),covered_entries=len(covered),
        boundaries=dict(Counter(p['reason'] for p in plans if not p['covered'])),slot_width=layout['slot_width'],
        static_shared_fields=sum(int((p['required']&~p['copied']).sum()) for p in covered),static_moved_fields=sum(int(p['copied'].sum()) for p in covered),
        static_mapping_bytes=sum(p['projection'].nbytes+p['required'].nbytes+p['copied'].nbytes for p in covered),
        added_directory_bytes_per_logical_cell=4*(layout['slot_width']+2),added_directory_bytes_per_physical_owner=5,
        source_logical_keys_retained=True,logical_activation_transfer=False,writable_owner_runtime=False,
        limitations=['Runtime exact values, scalar columns, generations, aliases and quiescence must still pass',
          'Batched fixed arenas release reusable capacity, not allocated process bytes',
          'More multi-source ownership candidates require actual matched slot-origin evidence'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
