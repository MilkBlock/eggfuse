"""Bounded constructor completion and token refresh between Entry rounds.

Unsupported effects stay pending at their original effect_pc. External witness
coverage and a settled Eq snapshot are caller obligations, not inferred here.
"""
from device_slot_owners import shape as slot_shape,read as read_slot,has as has_slot,ensure_roots
import numpy as np
from compile_constructor_sites import compile_sites
from device_witness_views import compile_view,project
from device_constructor_results import execute_site
from device_copy_effects import compile_copies,execute_copy
from device_input_features import compile_inputs
from device_semantic_template import token_required
from device_token_refresh import refresh
from device_eq_completion import compile_unions,union_inputs,close,finish_unions
from device_semantic_keys import compile_types


def compile_completion(recipe,width,include_unions=False):
    key_types,_=compile_types(recipe)
    compiled=compile_sites(recipe);sites=compiled['sites'];copies=compile_copies(recipe)
    operations=sorted([('construct',s) for s in sites]+[('copy',s) for s in copies['sites']],key=lambda pair:(pair[1]['rule'],pair[1]['operation']))
    views={(s['table'],len(s['args'])):compile_view(recipe,s['table'],len(s['args'])) for s in sites}
    union_marks=[]
    eq_types=None;closure_views=[];names=[]
    if include_unions:
        union_plan,union_marks=compile_unions(recipe)
        for i,rid in enumerate(union_plan['rule']):
            if rid<0:continue
            site={k:int(v[i]) if k!='last' else bool(v[i]) for k,v in union_plan.items()}
            site['plan']={k:v[i:i+1] for k,v in union_plan.items()}
            operations.append(('union',site))
        operations.sort(key=lambda pair:(pair[1]['rule'],pair[1]['operation']))
        names=sorted({s['sort']['name'] for r in recipe['rules'] for s in r['slots'] if s['sort']['kind']=='eq'})
        eq_types=np.full((len(recipe['rules']),width),-1,np.int32)
        for rid,r in enumerate(recipe['rules']):
            for slot,s in enumerate(r['slots']):
                if s['sort']['kind']=='eq':eq_types[rid,slot]=names.index(s['sort']['name'])
        tables={t['name']:i for i,t in enumerate(recipe['tables']) if t['kind']=='constructor'}
        occurrences=set(views)
        for r in recipe['rules']:
            for atom in r['query']:
                name=atom['call'].get('table')
                if name in tables:occurrences.add((tables[name],len(atom['args'])-1))
        closure_views=[compile_view(recipe,t,a) for t,a in sorted(occurrences)]
        for site in sites:site['result_sort']=int(eq_types[site['rule'],site['dst']])
    layouts=[]
    for rid in (range(len(recipe['rules'])) if include_unions else sorted({s['rule'] for _,s in operations})):

        rule=recipe['rules'][rid];n=len(rule['slots'])
        if n>width:raise ValueError('completion slot width too small')
        base=compile_inputs(rule)
        layout=dict(required=np.zeros((1,width),bool),eq=np.zeros((1,width),bool),sorts=np.full((1,width),-1,np.int32),
                    roles=np.zeros((1,width,64),np.float32),numeric_roles=np.zeros((1,width,64),np.float32))
        layout['required'][:,:n]=token_required(rule)
        for key in ('eq','sorts','numeric_roles'):layout[key][:,:n]=base[key]
        layout['roles'][:,:n]=base['roles'][:,:,:64]
        layouts.append((rid,layout))
    marks=[m for m in compiled['marks'] if m['reason']!='effect:copy' and not (include_unions and m['reason']=='effect:union')]+copies['marks']+union_marks
    return dict(sites=sites,operations=operations,views=views,layouts=layouts,marks=marks,eq_types=eq_types,closure_views=closure_views,include_unions=include_unions,eq_sort_names=names,key_types=key_types)


def complete(state,plan,next_id,limit,quota,external_complete,eq_settled,xp,eq_context=None,eq_rounds=4):
    if plan.get('include_unions',False) and eq_context is None:raise ValueError('union completion needs typed identity registry')
    if eq_context is not None:
        if not plan.get('include_unions',False):raise ValueError('registry requires typed completion plan')
        eq_context=dict(eq_context)
        limit=xp.minimum(limit,eq_context['roots'].shape[0])
        state=ensure_roots(state,xp)
    attention=xp.array(False);executed=xp.array(0,dtype=xp.int32)
    new_constructors=xp.array(0,dtype=xp.int32);new_equivalences=xp.array(0,dtype=xp.int32)
    for kind,site in plan['operations']:
        if kind=='union':
            pairs,active,missing=union_inputs(state,site['plan'],xp)
            ids=state['keys'][:,0];safe=xp.clip(ids,0,plan['eq_types'].shape[0]-1)
            types=plan['eq_types'][safe]
            eq_slots=(types>=0)&(ids[:,None]>=0)
            n,w=slot_shape(state);rr=xp.arange(n)[:,None];ss=xp.arange(w)[None,:]
            values=read_slot(state,'slots',rr,ss,xp);size=eq_context['roots'].shape[0]
            used=state['present'][:,None]&read_slot(state,'slot_valid',rr,ss,xp)&eq_slots
            bad_type=(values<0)|(values>=size)|(eq_context['sorts'][xp.clip(values,0,size-1)]!=types)
            typed_snapshot=~xp.any(used&bad_type)&~xp.any(state['present']&((ids<0)|(ids>=plan['eq_types'].shape[0])))
            requested=xp.any(active)
            required=requested&typed_snapshot
            active=active&typed_snapshot
            candidate,roots,closure=close(state,eq_context['roots'],eq_context['sorts'],eq_slots,pairs,active,plan['closure_views'],external_complete,eq_rounds,xp)
            state={k:xp.where(required,candidate[k],v) for k,v in state.items()}
            labels=xp.arange(roots.shape[0],dtype=roots.dtype)
            merged=xp.sum((eq_context['roots']==labels).astype(xp.int32))-xp.sum((roots==labels).astype(xp.int32))
            new_equivalences=new_equivalences+xp.where(required,xp.maximum(merged,0),0)
            eq_context['roots']=xp.where(required,roots,eq_context['roots'])
            eq_settled=xp.where(required,closure['settled'],eq_settled)
            state,ready=finish_unions(state,site['plan'],active,closure,xp)
            state['token_dirty']=state['token_dirty']|ready
            outcome=dict(ready=ready,needs_attention=(required&closure['needs_attention'])|(requested&~typed_snapshot)|xp.any(missing))
        elif kind=='copy':
            state,outcome=execute_copy(state,site,xp)
        else:
            view=project(state,plan['views'][(site['table'],len(site['args']))],external_complete,eq_settled,xp)
            state,outcome=execute_site(state,site,view,next_id,limit,quota,xp)
            if eq_context is not None:
                labels=xp.arange(eq_context['roots'].shape[0],dtype=eq_context['roots'].dtype)
                allocated=(labels>=next_id)&(labels<outcome['next_id'])
                eq_context['roots']=xp.where(allocated,labels,eq_context['roots'])
                eq_context['sorts']=xp.where(allocated,site['result_sort'],eq_context['sorts'])
            new_constructors=new_constructors+xp.sum(outcome['new_owner'].astype(xp.int32))
            next_id=outcome['next_id']
        attention=attention|outcome['needs_attention']
        executed=executed+xp.sum(outcome['ready'].astype(xp.int32))
    refreshed=xp.array(0,dtype=xp.int32)
    rows,width=slot_shape(state);rr=xp.arange(rows)[:,None];ss=xp.arange(width)[None,:]
    for rid,layout in plan['layouts']:
        selected=dict(state,present=state['present']&(state['keys'][:,0]==rid))
        codes=read_slot(state,'scalar_codes',rr,ss,xp) if has_slot(state,'scalar_codes') else xp.zeros((rows,width,64),xp.float32)
        valid=read_slot(state,'scalar_valid',rr,ss,xp) if has_slot(state,'scalar_valid') else xp.zeros((rows,width),xp.bool_)
        if has_slot(state,'scalar_numbers') and has_slot(state,'scalar_numeric'):
            number=read_slot(state,'scalar_numbers',rr,ss,xp);finite=xp.isfinite(number);safe=xp.where(finite,number,0)
            numeric=xp.tanh((xp.sign(safe)*xp.log1p(xp.abs(safe)))[:,:,None]*layout['numeric_roles'])
            codes=xp.where(read_slot(state,'scalar_numeric',rr,ss,xp)[:,:,None],numeric,codes)
            valid=xp.where(read_slot(state,'scalar_numeric',rr,ss,xp),finite,valid)
        updated,marks=refresh(selected,layout['sorts'],layout['eq'],layout['required'],layout['roles'],codes,valid,eq_settled,xp,retain_prediction=rid in plan.get('retain_predicted_rules',()))
        updated['present']=state['present'];state=updated
        refreshed=refreshed+xp.sum(marks['refreshed'].astype(xp.int32))
        attention=attention|marks['needs_attention']
    pending=state['present']&state['active']&(~state['settled']|state.get('token_dirty',xp.zeros_like(state['present'])))
    result=dict(executed=executed,refreshed=refreshed,new_constructors=new_constructors,new_equivalences=new_equivalences,semantic_changed=(new_constructors>0)|(new_equivalences>0),needs_attention=attention|xp.any(pending),pending=pending)
    if eq_context is not None:result.update(eq_context=eq_context,eq_settled=eq_settled)
    return state,next_id,result
