"""One bounded, entirely device-selected neural Cell admission.

Templates/models are host-compiled; runtime values stay on device. A step
admits at most one novel instance of one rule. No-admission is NOT saturation.
"""
from neural_device_candidates import candidates
from device_neural_speculation import frame_payload,install


def key_view(keys,roots,xp):
    values=keys[:,1:]
    valid=xp.all((values==-1)|((values>=0)&(values<len(roots))),axis=1)
    mapped=xp.where(values>=0,roots[xp.clip(values,0,len(roots)-1)],-1)
    return xp.concatenate([keys[:,:1],mapped],axis=1),valid


def advance(state,roots,next_id,frames,query_plan,frame_plan,rule_id,model,eq_head,enabled,xp,capture=False):
    batch=candidates(state,frames,query_plan,xp.array(True),xp.array(True),xp)
    logits,tokens=model.transition(batch['tokens'],batch['edges'],batch['mask'],batch['request'],batch['relations'])
    scores=eq_head(tokens,batch['request'])
    finite=xp.isfinite(logits)&xp.all(xp.isfinite(tokens),axis=1)&xp.all(xp.isfinite(scores),axis=1)
    eligible=batch['live']&batch['constraints_satisfied']&(logits>=0)&finite
    n=len(logits);padding=state['keys'].shape[1]-1-batch['binding_roots'].shape[1]
    keys=xp.concatenate([xp.full((n,1),rule_id,xp.int32),batch['binding_roots'],xp.full((n,padding),-1,xp.int32)],axis=1)
    proposed,valid=key_view(keys,roots,xp);resident,resident_valid=key_view(state['keys'],roots,xp)
    known=xp.any(xp.all(proposed[:,None,:]==resident[None,:,:],axis=2)&state['present'][None,:],axis=1)
    novel=eligible&valid&~known
    dirty=xp.any(state['present']&state.get('token_dirty',xp.zeros_like(state['present'])))
    blocked=(~batch['complete']|dirty|xp.any(batch['live']&~finite)
             |xp.any(state['present']&~resident_valid)|xp.any(eligible&~valid))
    selected=xp.argmax(novel.astype(xp.int32));requested=enabled&~blocked&xp.any(novel)
    context_invalid=xp.array(False)
    context_depth=max((s.get('context_depth',0) for s in frame_plan['witness_sites'].values()),default=0)
    if context_depth:
        from device_witness_context import inspect
        context_invalid=inspect(state,batch['sources'][selected],batch['mask'][selected],batch['generations'][selected],context_depth,xp)[3]
    payload,proposed_roots,ready=frame_payload(state,frame_plan,batch,selected,scores[selected],next_id,roots,xp)
    result,marks=install(state,payload,proposed_roots,batch,selected,tokens[selected],rule_id,frame_plan['inputs'],ready&requested&~context_invalid,xp)
    accepted=xp.any(marks['accepted'])
    event=dict(
        admitted=accepted,audit_pending=accepted,selected=selected,
        key=keys[selected],result_slots=payload["slots"][0],result_valid=payload["slot_valid"][0],
        result_roots=proposed_roots[xp.clip(payload['slots'][0],0,len(proposed_roots)-1)],
        duplicate_candidates=xp.sum((eligible&known).astype(xp.int32)),
        no_novel_proposal=enabled&~blocked&~xp.any(novel),
        needs_attention=enabled&(blocked|(requested&~accepted)|marks['token_refresh_required']),
        stale_witness_context=requested&context_invalid,
        query_overflow=enabled&batch['overflow'],pool_sizes=batch['pool_sizes'],
        query_incomplete=enabled&~batch['complete'],dirty_input=enabled&dirty,
        nonfinite=enabled&xp.any(batch['live']&~finite),
        invalid_keys=enabled&(xp.any(state['present']&~resident_valid)|xp.any(eligible&~valid)),
        rejected_proposal=requested&~accepted,
        capacity=xp.any(marks['capacity'])|(requested&((next_id<0)|(next_id>len(roots)-payload['slots'].shape[1]))),
        payload_invalid=requested&~ready&(next_id>=0)&(next_id<=len(roots)-payload['slots'].shape[1]),
        token_refresh_required=marks['token_refresh_required'])
    if capture:event.update(output_token=tokens[selected],request=batch['request'][selected])
    return result,xp.where(accepted,proposed_roots,roots),xp.where(accepted,next_id+payload['slots'].shape[1],next_id),event
