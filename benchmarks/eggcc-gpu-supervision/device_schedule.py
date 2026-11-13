"""Fixed control table for nested source schedules, with device-owned loop state.

A RUN advances only on an externally established completed Run result. Logical
matches, predicted tokens and merely exhausted budgets are not that result.
"""
import numpy as np
RUN,ENTER_SAT,END_SAT,ENTER_REPEAT,END_REPEAT,HALT=range(6)


def compile_schedule(control,stages):
    if len(set(stages))!=len(stages):raise ValueError('duplicate stage names')
    code=[];sat_count=repeat_count=0
    def emit(op,stage=-1,slot=0,arg=0,jump=0,scope=()):
        code.append(dict(op=op,stage=stage,slot=slot,arg=arg,jump=jump,scope=scope));return len(code)-1
    def visit(node,scope):
        nonlocal sat_count,repeat_count
        if isinstance(node,list):
            for child in node:visit(child,scope)
            return
        if not isinstance(node,dict):raise ValueError('invalid schedule node')
        keys=set(node)
        if keys=={'sequence'}:
            if not isinstance(node['sequence'],list):raise ValueError('invalid sequence')
            visit(node['sequence'],scope)
        elif keys=={'run'}:
            if node['run'] not in stages:raise ValueError('unknown ruleset')
            emit(RUN,stage=stages.index(node['run']),scope=scope)
        elif keys=={'saturate'}:
            slot=sat_count;sat_count+=1;start=emit(ENTER_SAT,slot=slot)
            visit(node['saturate'],scope+(slot,));emit(END_SAT,slot=slot,jump=start)
        elif keys=={'repeat','body'}:
            count=node['repeat']
            if type(count) is not int or not 0<=count<=np.iinfo(np.int32).max:raise ValueError('invalid repeat count')
            slot=repeat_count;repeat_count+=1;start=emit(ENTER_REPEAT,slot=slot,arg=count)
            visit(node['body'],scope);emit(END_REPEAT,slot=slot,jump=start+1)
            code[start]['jump']=len(code)
        else:raise ValueError('unsupported source control form')
    visit(control,());emit(HALT)
    scope=np.zeros((len(code),max(1,sat_count)),bool)
    for i,ins in enumerate(code):scope[i,list(ins['scope'])]=True
    out={k:np.array([ins[k] for ins in code],np.int32) for k in ('op','stage','slot','arg','jump')}
    out['scope']=scope
    return out,dict(stages=stages,saturation_slots=sat_count,repeat_slots=repeat_count,instructions=len(code))


def initial(plan,repeat_slots,xp):
    return dict(pc=xp.array(0,dtype=xp.int32),changed=xp.zeros(plan['scope'].shape[1],xp.bool_),remaining=xp.zeros(max(1,repeat_slots),xp.int32))


def current(state,plan,xp):
    valid=(state['pc']>=0)&(state['pc']<plan['op'].shape[0]);pc=xp.clip(state['pc'],0,plan['op'].shape[0]-1)
    op=plan['op'][pc]
    return xp.where(valid&(op==RUN),plan['stage'][pc],-1),valid&(op==HALT)


def tick(state,plan,run_done,run_changed,xp):
    run_done=xp.array(run_done,dtype=xp.bool_);run_changed=xp.array(run_changed,dtype=xp.bool_)
    valid=(state['pc']>=0)&(state['pc']<plan['op'].shape[0]);pc=xp.clip(state['pc'],0,plan['op'].shape[0]-1)
    op=plan['op'][pc];slot=plan['slot'][pc]
    sat=xp.clip(slot,0,state['changed'].shape[0]-1);rep=xp.clip(slot,0,state['remaining'].shape[0]-1)
    done=valid&(op==RUN)&run_done
    changed=state['changed']|(plan['scope'][pc]&done&run_changed)
    changed=xp.where((op==ENTER_SAT)&(xp.arange(changed.shape[0])==sat)&valid,False,changed)
    remaining=state['remaining']
    value=xp.maximum(remaining[rep]-1,0)
    remaining=xp.where((op==ENTER_REPEAT)&valid&(xp.arange(remaining.shape[0])==rep),plan['arg'][pc],remaining)
    remaining=xp.where((op==END_REPEAT)&valid&(xp.arange(remaining.shape[0])==rep),value,remaining)
    next_pc=pc+1
    next_pc=xp.where((op==RUN)&~run_done,pc,next_pc)
    next_pc=xp.where((op==END_SAT)&changed[sat],plan['jump'][pc],next_pc)
    next_pc=xp.where((op==ENTER_REPEAT)&(plan['arg'][pc]==0),plan['jump'][pc],next_pc)
    next_pc=xp.where((op==END_REPEAT)&(value>0),plan['jump'][pc],next_pc)
    next_pc=xp.where((op==HALT)|~valid,state['pc'],next_pc)
    return dict(pc=next_pc,changed=changed,remaining=remaining),dict(run_consumed=done,invalid_pc=~valid,waiting=valid&(op==RUN)&~run_done)
