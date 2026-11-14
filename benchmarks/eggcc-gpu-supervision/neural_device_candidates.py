"""Neural candidate features from live Cell/owner projections on device.

Static query routes select constructor views, not CPU successful bindings.
Ordered identity incidence and whole source tokens enter the learned transition.
The bounded Cartesian candidate pool is diagnostic, not scalable routing.
"""
import numpy as np
from device_witness_views import compile_view,project
from device_slot_owners import read,shape
from neural_snapshot_candidates import relational_edges
from neural_ordered_relations import demand,incidence
from multi_entry_ridge import template,vec


def compile_frames(recipe,width):
    roles=np.zeros((len(recipe['rules']),width,64),np.float32)
    numeric=np.zeros_like(roles);valid=np.zeros((len(roles),width),bool);eq=np.zeros_like(valid);seed=np.zeros(len(roles),bool)
    for rid,rule in enumerate(recipe['rules']):
        semantic=rule.get('token_layout',{}).get('rule',rule)
        n=len(semantic['slots']);roles[rid,:n]=template(semantic)[0];valid[rid,:n]=True
        seed[rid]=rule.get('metadata',{}).get('source_set')=='snapshot'
        for slot,s in enumerate(semantic['slots']):
            eq[rid,slot]=s['sort']['kind']=='eq';numeric[rid,slot]=vec(('numeric',s['sort']['name']))
    return dict(roles=roles,numeric=numeric,valid=valid,eq=eq,seed=seed,max_seed_width=max((len(r['slots']) for r in recipe['rules'] if r.get('metadata',{}).get('source_set')=='snapshot'),default=0))


def seed_inputs(state,layout,xp,field_width=5):
    if layout['max_seed_width']>field_width:raise ValueError('seed interface exceeds encoder width')
    n,width=shape(state);rr=xp.arange(n)[:,None];ss=xp.arange(width)[None,:]
    rid=xp.clip(state['keys'][:,0],0,len(layout['roles'])-1)
    roots=read(state,'slot_roots',rr,ss,xp)
    valid=read(state,'slot_valid',rr,ss,xp)&layout['valid'][rid]
    roles=layout['roles'][rid]
    same=(roots[:,:,None]==roots[:,None,:])&valid[:,:,None]&valid[:,None,:]
    context=same.astype(xp.float32)@roles
    codes=read(state,'scalar_codes',rr,ss,xp)
    numbers=read(state,'scalar_numbers',rr,ss,xp)
    numeric=xp.tanh((xp.sign(numbers)*xp.log1p(xp.abs(numbers)))[:,:,None]*layout['numeric'][rid])
    codes=xp.where(read(state,'scalar_numeric',rr,ss,xp)[:,:,None],numeric,codes)
    dynamic=xp.tanh(xp.where(layout['eq'][rid,:,None],context,codes))
    fields=xp.concatenate([roles,dynamic],axis=-1)
    fields=xp.where(valid[:,:,None],fields,0)[:,:field_width]
    if width<field_width:fields=xp.concatenate([fields,xp.zeros((n,field_width-width,128),xp.float32)],axis=1)
    update=state['present']&layout['seed'][rid]
    return fields.reshape(n,field_width*128),update


def encode_seeds(state,layout,model,xp,field_width=5):
    fields,update=seed_inputs(state,layout,xp,field_width)
    token=model.encode(fields)
    return dict(state,tokens=xp.where(update[:,None],token,state['tokens']))


def input_role_tags(atoms,context_capacity):
    if not context_capacity:return np.zeros((atoms,128),np.float32)
    roles=[('query',i) for i in range(atoms)]+[('context',)]*context_capacity
    return np.array([np.concatenate([vec(('cell-input-role',role,j)) for j in (0,1)]) for role in roles],np.float32)


def compile_candidates(recipe,consumer,capacity=16,atoms=2,fields=5,context_capacity=0):
    if not 1<=len(consumer['query'])<=atoms or capacity<1 or context_capacity<0:raise ValueError('candidate shape')
    tables={t['name']:i for i,t in enumerate(recipe['tables'])};views=[];origins={}
    for ai,a in enumerate(consumer['query']):
        if len(a['args'])>fields or any('slot' not in x for x in a['args']):raise ValueError('unsupported query projection')
        views.append(compile_view(recipe,tables[a['call']['table']],len(a['args'])-1))
        for fi,arg in enumerate(a['args']):origins.setdefault(arg['slot'],(ai,fi))
    inputs=[s for s,d in enumerate(consumer['slots']) if d['definition']=='query']
    if set(inputs)!=set(origins):raise ValueError('incomplete input projection')
    return dict(views=views,capacity=capacity,atoms=atoms,fields=fields,inputs=inputs,origins=origins,context_capacity=context_capacity,
                required=demand(consumer,atoms,fields),request=template(consumer)[1],source_tags=input_role_tags(atoms,context_capacity))


def candidates(state,frames,plan,external_complete,eq_settled,xp):
    cap=plan['capacity'];count=cap**len(plan['views']);ordinal=xp.arange(count)
    views=[];complete=xp.array(True);overflow=xp.array(False)
    for view_plan in plan['views']:
        v=project(state,view_plan,external_complete,eq_settled,xp,include_fields=True);n=len(v['live'])
        # Prefer the later producer for duplicate facts, retaining generated tokens.
        same=xp.all(v['value_roots'][:,None,:]==v['value_roots'][None,:,:],axis=-1)
        later=xp.arange(n)[None,:]>xp.arange(n)[:,None]
        ready=state['settled']&~state.get('token_dirty',xp.zeros_like(state['settled']))
        eligible=v['live']&ready[v['source']]
        complete=complete&~xp.any(v['live']&~ready[v['source']])
        keep=eligible&~xp.any(same&later&eligible[None,:],axis=1)
        order=xp.sort(xp.where(keep,n-1-xp.arange(n),n))[:cap]
        if len(order)<cap:order=xp.concatenate([order,xp.full((cap-len(order),),n,xp.int32)])
        pick=xp.clip(n-1-order,0,n-1)
        views.append(dict(v,pick=pick,selected=order<n))
        overflow=overflow|(xp.sum(keep.astype(xp.int32))>cap);complete=complete&v['complete']
    sources=[];projected=[];raw=[];positions=[];alive=xp.ones(count,xp.bool_)
    for ai,v in enumerate(views):
        lane=(ordinal//(cap**(len(views)-1-ai)))%cap;pick=v['pick'][lane]
        sources.append(v['source'][pick]);alive=alive&v['selected'][lane]&state['settled'][v['source'][pick]]
        fields=v['value_roots'][pick];padding=plan['fields']-fields.shape[1]
        projected.append(xp.concatenate([fields,xp.full((count,padding),-1,xp.int32)],axis=1));raw.append(v['values'][pick]);positions.append(v['source_slots'][pick])
    for _ in range(plan['atoms']-len(views)):
        sources.append(xp.zeros(count,xp.int32));projected.append(xp.full((count,plan['fields']),-1,xp.int32))
    sources=xp.stack(sources,axis=1);projected=xp.stack(projected,axis=1)
    mask=xp.broadcast_to(xp.arange(plan['atoms'])<len(views),(count,plan['atoms']))
    n,width=shape(state);rr=xp.arange(n)[:,None];ss=xp.arange(width)[None,:]
    context_overflow=xp.array(False)
    if plan['context_capacity']:
        k=plan['context_capacity'];row=xp.arange(n)
        used=xp.any((sources[:,:,None]==row[None,None,:])&mask[:,:,None],axis=1)
        eligible=state['present']&state['visible']&ready
        extra=eligible[None,:]&~used
        order=xp.sort(xp.where(extra,n-1-row[None,:],n),axis=1)[:,:k]
        if order.shape[1]<k:order=xp.concatenate([order,xp.full((count,k-order.shape[1]),n,xp.int32)],axis=1)
        selected=order<n;pick=xp.clip(n-1-order,0,n-1)
        sources=xp.concatenate([sources,pick],axis=1);mask=xp.concatenate([mask,selected],axis=1)
        context_overflow=xp.any(alive&(xp.sum(extra.astype(xp.int32),axis=1)>k))
        # Unsettled resident context is not silently treated as absent.
        complete=complete&~xp.any(state['present']&state['visible']&~ready)
    rid=xp.clip(state['keys'][:,0],0,len(frames['roles'])-1)
    valid=read(state,'slot_valid',rr,ss,xp)&frames['valid'][rid]
    labels=xp.where(valid,read(state,'slot_roots',rr,ss,xp),-1)
    edges=relational_edges(labels,frames['roles'][rid],sources)
    binding=xp.stack([projected[:,plan['origins'][s][0],plan['origins'][s][1]] for s in plan['inputs']],axis=1)
    binding_sources=xp.stack([sources[:,plan['origins'][s][0]] for s in plan['inputs']],axis=1)
    binding_slots=xp.stack([positions[plan['origins'][s][0]][:,plan['origins'][s][1]] for s in plan['inputs']],axis=1)
    return dict(tokens=state['tokens'][sources]+plan['source_tags'][None,:,:],source_tags=xp.broadcast_to(plan['source_tags'],(count,sources.shape[1],128)),edges=edges,mask=mask,request=xp.broadcast_to(plan['request'],(count,64)),
                relations=incidence(projected,plan['required'],xp),sources=sources,generations=state['generation'][sources],binding_roots=binding,binding_sources=binding_sources,binding_slots=binding_slots,
                live=alive,complete=complete&~overflow&~context_overflow,overflow=overflow,context_overflow=context_overflow)
