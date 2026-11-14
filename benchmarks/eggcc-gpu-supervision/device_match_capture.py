"""Opt-in GPU match training capture. No persistent runtime registry or host reads."""
import numpy as np
from device_slot_owners import shape,read,live as owner_live


def collect(state,bindings,request,tokens,numerical,plan,xp,boundary_capture=None):
    rows=bindings['witness_rows'];safe=xp.clip(rows,0,state['tokens'].shape[0]-1)
    fields=xp.arange(shape(state)[1])[None,None,:]
    witness={k:read(state,k,safe[:,:,None],fields,xp) for k in ('slots','slot_roots','slot_valid')}
    for key in ('generation','present','visible','settled','effect_pc','token_dirty'):
        witness[key]=state[key][safe]
    witness['owner_live']=owner_live(state,safe,xp)
    witness['rule']=state['keys'][safe,0]
    if 'slot_owner' in state:
        owner=state['slot_owner'][safe];physical=xp.clip(owner,0,len(state['owner_live'])-1)
        witness.update(physical_owner=owner,owner_capacity=xp.array(len(state['owner_live'])),
            owner_epoch=state['owner_epoch'][safe],physical_generation=state['owner_generation'][physical],physical_live=state['owner_live'][physical])
    src=xp.clip(request['sources'],0,state['tokens'].shape[0]-1)
    ports=[p['slot'] for p in plan['ports']]
    result=dict(rule=xp.array(plan['query']['rule']),source_capacity=xp.array(state['tokens'].shape[0]),bindings=bindings,request=request,
        source_tokens=state['tokens'][src],source_rules=state['keys'][src,0],
        input_ports=xp.array(ports,xp.int32),source_ports=bindings['source_slots'][:,ports],
        predicted_tokens=tokens,numerical_ready=numerical['ready'],witness=witness)
    if 'owner_relation' in request:
        from device_owner_relations import snapshot as owner_snapshot
        result['source_owner_context']=owner_snapshot(state,request['sources'],request['edge_valid'],xp)
    if boundary_capture is not None:
        result.update(boundary_capture)
    elif 'boundary_context' in plan:
        from device_boundary_context import snapshot,encode
        boundary=snapshot(state,xp)
        features,counts=encode(boundary,bindings,plan['boundary_context'],xp)
        result.update(boundary=boundary,boundary_features=features,boundary_counts=counts)
    return result


def host(value):
    if isinstance(value,dict):return {k:host(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [host(v) for v in value]
    return np.array(value)


def audit(recipe,capture):
    """Independently decode selected source Cell facts and check the entire join.

    This validates the captured snapshot, not a subsequent source lifetime.
    It does not certify missing matches or a rule's effects.
    """
    c=host(capture);b=c['bindings'];w=c['witness'];r=c['request']
    rid=int(c['rule']);rule=recipe['rules'][rid];errors=[];checked=0
    records={}
    for atom in rule['query']:
        name=atom['call']['table']
        if name in records:continue
        entries=[]
        for ri,source in enumerate(recipe['rules']):
            entries.extend((ri,-1,q['args']) for q in source['query'] if q['call'].get('table')==name)
            for oi,op in enumerate(source['effects']):
                if op.get('call',{}).get('table')==name and op['kind'] in ('construct','set'):
                    entries.append((ri,oi,[*op['args'],dict(slot=op['dst']) if op['kind']=='construct' else op['value']]))
        records[name]=entries
    matched=np.flatnonzero(b['live'])
    for lane in matched:
        checked+=1
        if 'owner_relation' in r:
            owner=c.get('source_owner_context')
            if owner is None:errors.append('missing_owner_context')
            else:
                for pi in np.flatnonzero(r['edge_valid'][lane]):
                    matches=np.flatnonzero(b['witness_rows'][lane]==r['sources'][lane,pi])
                    if not len(matches):errors.append('owner_source_not_witness');continue
                    ai=int(matches[0])
                    expected=w['physical_owner'][lane,ai] if 'physical_owner' in w else b['witness_rows'][lane,ai]
                    epoch=w['owner_epoch'][lane,ai] if 'owner_epoch' in w else w['generation'][lane,ai]
                    generation=w['physical_generation'][lane,ai] if 'physical_generation' in w else w['generation'][lane,ai]
                    if (owner['owners'][lane,pi]!=expected or owner['owner_epoch'][lane,pi]!=epoch or
                        owner['physical_generation'][lane,pi]!=generation or not owner['physical_live'][lane,pi] or
                        not owner['usable'][lane,pi] or owner['missing'][lane]):errors.append('owner_context_mismatch')
        for slot,value in rule.get('query_literal_guards',{}).items():
            expected=recipe.get('literal_ids',{}).get(value,-1)
            if expected<0 or not b['slot_valid'][lane,int(slot)] or int(b['slots'][lane,int(slot)])!=expected:errors.append('literal_guard')
        for ai,atom in enumerate(rule['query']):
            row=int(b['witness_rows'][lane,ai]);sr=int(w['rule'][lane,ai])
            if not 0<=row<int(c['source_capacity']) or not 0<=sr<len(recipe['rules']):errors.append('source_address');continue
            if not all(bool(w[k][lane,ai]) for k in ('present','visible','settled','owner_live')) or w['token_dirty'][lane,ai]:errors.append('source_lifecycle')
            if w['generation'][lane,ai]!=b['witness_generations'][lane,ai]:errors.append('source_generation')
            if 'physical_owner' in w:
                if not 0<=w['physical_owner'][lane,ai]<w['owner_capacity'] or not w['physical_live'][lane,ai] or w['owner_epoch'][lane,ai]!=w['physical_generation'][lane,ai]:errors.append('physical_owner_generation')
            source=recipe['rules'][sr];pc=len(source['effects']) if w['settled'][lane,ai] else int(w['effect_pc'][lane,ai])
            entries=records[atom['call']['table']];record=int(b['witness_records'][lane,ai])
            if not 0<=record<len(entries) or entries[record][0]!=sr:
                errors.append('witness_record');continue
            _,oi,args=entries[record]
            candidates=[(oi,args)] if oi<pc else []
            found=False
            for oi,args in candidates:
                if len(args)!=len(atom['args']) or any('slot' not in a for a in args):continue
                slots=[a['slot'] for a in args]
                if any(op.get('dst') in slots for op in source['effects'][oi+1:pc]):continue
                if not all(w['slot_valid'][lane,ai,s] for s in slots):continue
                ok=True
                for dst,src in zip(atom['args'],slots):
                    slot=dst['slot'];eq=rule['slots'][slot]['sort']['kind']=='eq'
                    column='slot_roots' if eq else 'slots'
                    if not b['slot_valid'][lane,slot] or b[column][lane,slot]!=w[column][lane,ai,src]:ok=False;break
                found |= ok
            if not found:errors.append('joint_atom_mismatch')
        for pi,slot in enumerate(c['input_ports']):
            origin=next((ai,field) for ai,a in enumerate(rule['query']) for field,v in enumerate(a['args']) if v['slot']==slot)
            ai,field=origin
            entries=records[rule['query'][ai]['call']['table']];record=int(b['witness_records'][lane,ai])
            if 0<=record<len(entries) and 'slot' in entries[record][2][field]:
                if c['source_ports'][lane,pi]!=entries[record][2][field]['slot']:errors.append('input_record_port')
            if r['sources'][lane,pi]!=b['witness_rows'][lane,ai] or r['sources'][lane,pi]!=b['source_rows'][lane,slot]:errors.append('input_source')
            if r['generations'][lane,pi]!=w['generation'][lane,ai] or b['source_generations'][lane,slot]!=w['generation'][lane,ai]:errors.append('input_generation')
            pos=int(c['source_ports'][lane,pi])
            if pos!=b['source_slots'][lane,slot] or not 0<=pos<w['slots'].shape[-1]:errors.append('input_port');continue
            if c['source_rules'][lane,pi]!=w['rule'][lane,ai]:errors.append('input_source_rule')
            if not w['slot_valid'][lane,ai,pos] or b['slots'][lane,slot]!=w['slots'][lane,ai,pos] or b['slot_roots'][lane,slot]!=w['slot_roots'][lane,ai,pos]:errors.append('input_value')
        if not c['numerical_ready'][lane]:errors.append('numerical_not_ready')
    from collections import Counter
    return dict(checked=checked,errors=dict(Counter(errors)),passed=not errors,
        enumeration_complete=bool(b['complete']),overflow=bool(b['overflow']),
        accepted=int(np.count_nonzero(c.get('accepted',np.zeros_like(b['live'])))),
        scope='selected snapshot witness soundness; not exhaustive enumeration, effects or future lifetime')


def floating_inputs(capture,model,xp):
    """Reconstruct exactly the selected-source floating inputs, no target labels."""
    from multi_entry_ridge import features
    c=capture;r=c['request'];mask=r['edge_valid']
    edge=xp.where(mask[:,:,None],r['edge'],0);route=xp.where(mask[:,:,None],r['route'],0)
    values=xp.where(mask[:,:,None],c['source_tokens'],0)
    count=xp.maximum(xp.sum(mask.astype(xp.float32),axis=1),1)
    pool=((xp.swapaxes(route,1,2)@(values*edge))/xp.sqrt(count[:,None,None])).reshape(mask.shape[0],-1)
    q=r['q']
    if 'source_relation' in r:
        from device_source_relations import encode
        q=xp.concatenate([q,encode(r['sources'],r['source_relation'],mask,xp)],axis=1)
    if 'owner_relation' in r:
        from device_source_relations import encode
        if 'source_owner_context' not in c:raise ValueError('missing captured physical owner context')
        owner=c['source_owner_context']
        q=xp.concatenate([q,encode(owner['owners'],r['owner_relation'],owner['usable'],xp)],axis=1)
    x=features(r['seed'],q,pool,model['w'],xp)
    if 'boundary_features' in r:x=xp.concatenate([x,r['boundary_features']],axis=1)
    if 'shared_boundary_features' in r:x=xp.concatenate([x,r['shared_boundary_features']],axis=1)
    return x


def flatten(value,prefix=''):
    if isinstance(value,dict):
        return {name:array for k,v in value.items() for name,array in flatten(v,prefix+str(k)+'/').items()}
    if isinstance(value,(tuple,list)):
        return {name:array for k,v in enumerate(value) for name,array in flatten(v,prefix+str(k)+'/').items()}
    return {prefix.rstrip('/'):np.array(value)}


def partition(trace,manifest_path):
    import hashlib,json
    from pathlib import Path
    from collect_observed_corpus import read_bytes
    raw=manifest_path.read_bytes();manifest=json.loads(raw)
    matches=[c for c in manifest['cases'] if c.get('program_sha256')==trace['program_sha256']]
    if len(matches)!=1 or matches[0]['status']!='complete':raise ValueError('capture corpus membership')
    case=matches[0]
    if case['split'] not in ('train','validation','test'):raise ValueError('capture partition')
    program=read_bytes(Path(case['program']))
    original=json.loads(program)
    # Program sha256 is the compiler's internal fingerprint, not the JSON file hash.
    if original['sha256']!=case['program_sha256']:raise ValueError('capture program fingerprint')
    if original['recipe']!=trace['recipe']:raise ValueError('capture recipe mismatch')
    return dict(case=case['case'],partition=case['split'],corpus_manifest_sha256=hashlib.sha256(raw).hexdigest(),program_file_sha256=hashlib.sha256(program).hexdigest())
