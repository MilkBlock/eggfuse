"""Freeze observable source-port issuance separately from subsequent committed consumption."""
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
def compile_branches(spec,lits):
    equals={};greater={}
    for rid,rule in enumerate(spec['rules']):
        q=rule['q']
        if not q or not isinstance(q[0][0],int):continue
        table,args=q[0];types=spec['tables'][table]['schema']
        if spec['tables'][table]['kind']!='constructor' or args[-1]<0:continue
        slots=[v for v in args if v>=0]
        if len(slots)!=len(set(slots)):continue
        constants=[i for i,v in enumerate(args[:-1]) if v<0]
        if len(q)==1 and len(constants)==1:
            i=constants[0]
            if types[i]['name']=='i64':equals[table,i,int(lits[-1-args[i]])]=rid
        if len(q)==2 and q[1][0]=='>' and not constants:
            x,threshold,_=q[1][1]
            if x in args[:-1] and threshold<0 and types[args.index(x)]['name']=='i64':
                greater[table,args.index(x),int(lits[-1-threshold])]=rid
    return {k:(equals[k],greater[k]) for k in equals.keys()&greater.keys()}


@dataclass
class Ports:
    # run, publication ticket, producer rule, effect port, physical row, b, a,
    # threshold, sibling literal, b statically known, a statically known, RHS ordinal
    events: np.ndarray
    branches: tuple
    optional: int


def producer_fields(rule,bind,effect,lits,columns):
    env={slot:int(bind[4+i]) for i,slot in enumerate(rule['inputs'])}
    def get(a):
        return int(lits[-1-a]) if a<0 else env.get(a)
    for op,fn,dst,args in rule['e'][:effect]:
        if op=='copy':env[dst]=get(args[0])
        elif op=='compute' and fn in ('+','-','*','min','max'):
            x,y=map(get,args)
            if x is not None and y is not None:
                env[dst]={'+':x+y,'-':x-y,'*':x*y,'min':min(x,y),'max':max(x,y)}[fn]
    op,_,_,args=rule['e'][effect]
    if op not in ('construct','set'):raise ValueError(op)
    result=[(get(args[i]),args[i]<0) for i in columns]
    if any(v is None for v,_ in result):raise ValueError('value unavailable at producer')
    return result


def read_ports(image,capture):
    spec=json.loads((image/'ingress.json').read_bytes())
    with np.load(image/'device.npz') as z:lits=z['lits']
    contracts=compile_branches(spec,lits)
    choices=[]
    for (table,col,k),pair in contracts.items():
        candidates=[e for e in spec['stage_entries'] if e['table']==spec['tables'][table]['name'] and e['rule'] not in pair]
        for entry in candidates:
            rule=spec['rules'][entry['rule']];_,args=rule['q'][entry['anchor']]
            other=[(i,int(lits[-1-v])) for i,v in enumerate(args[:-1]) if v<0 and i!=col and spec['tables'][table]['schema'][i]['name']=='i64']
            if len(other)==1:choices.append((table,col,k,pair,entry['rule'],*other[0]))
    if len(choices)!=1:raise ValueError(f'expected one guarded source-port family, found {choices}')
    table,col,k,pair,optional,sibling,sibling_lit=choices[0]
    # Source uses only the already committed binding and publication ticket. No later
    # consumer, final row, final graph, or learned success label enters the observation.
    with np.load(capture/'output.npz') as z:rhs=z['rhs']
    with np.load(capture/'neural-inputs.npz') as z:published=z['publications']
    events=[]
    for ticket,(ordinal,effect,row,t) in enumerate(published,1):
        if t!=table:continue
        binding=rhs[ordinal-1];run,rid=map(int,binding[:2]);rule=spec['rules'][rid]
        (value,static),(adjacent,adj_static)=producer_fields(rule,binding,int(effect),lits,[col,sibling])
        events.append([run,ticket,rid,int(effect),int(row),value,adjacent,int(k),sibling_lit,static,adj_static,int(ordinal)])
    return Ports(np.asarray(events,dtype=np.int64),tuple(pair),int(optional))


def later_labels(capture,ports):
    with np.load(capture/'neural-inputs.npz') as z:consumed=z['consumed']
    with np.load(capture/'output.npz') as z:rhs=z['rhs']
    index={int(r[1]):i for i,r in enumerate(ports.events)}
    # Multiple source RHS may consume the same physical publication and rule. One
    # proposed action can preselect one distinct consumer, not every such ordinal.
    counts=np.zeros((len(index),3),dtype=np.int32)
    first=np.zeros(len(index),np.int32)
    candidates=(*ports.branches,ports.optional)
    for ordinal,t in enumerate(consumed):
        i=index.get(int(t))
        if i is None:continue
        run,rule=map(int,rhs[ordinal,:2])
        assert run>ports.events[i,0]
        if rule not in candidates:raise ValueError(('unmodeled actual consumer',rule))
        j=candidates.index(rule);counts[i,j]+=1
        if not first[i]:first[i]=j+1
    y=counts>0
    b,threshold=ports.events[:,5],ports.events[:,7]
    assert not np.any(y[:,0]&(b!=threshold)) and not np.any(y[:,1]&(b<=threshold))
    assert not np.any(y[:,2]&(ports.events[:,6]!=ports.events[:,8]))
    assert not np.any(y[:,0]&y[:,1])
    return y,counts,first


def neural_origin(capture,online,ports):
    with np.load(online/'neural-output.npz') as z:roots=set(map(int,z['rhs_ordinal'].flatten()))-{0}
    with np.load(online/'compound-output.npz') as z:children=set(map(int,z['claims'][:,:,7].flatten()))-{0}
    assert not roots&children
    with np.load(online/'output.npz') as a,np.load(capture/'output.npz') as b:
        actual,src=a['rhs'],b['rhs']
        np.testing.assert_array_equal(actual[:,:2],src[:,:2]);np.testing.assert_array_equal(actual[:,4:],src[:,4:])
        won={o for o in roots|children if src[o-1,3]==actual[o-1,3]}
    return np.asarray([int(x) in won for x in ports.events[:,11]])


def observable_features(events,vocab):
    previous={}
    counts={}
    ids=[];features=[]
    for run,ticket,rid,effect,row,b,a,k,sib_lit,known,adj_known,ordinal in events:
        ids.append(vocab.get((int(rid),int(effect)),0))
        key=int(row)
        age=int(run)-previous.get(key,int(run));seen=counts.get(key,0)
        features.append([np.log1p(run)/8,np.log1p(seen)/4,min(age,128)/128.,float(seen==0),
                         float(known),float(adj_known),float(known)*np.tanh((b-k)/4.),
                         float(adj_known)*np.tanh((a-sib_lit)/4.)])
        previous[key]=int(run);counts[key]=seen+1
    return np.asarray(ids,np.int64),np.asarray(features,np.float32)
