"""Static Bake wiring for numerical output occupancy / direct-union hints.

These floating features are not Eq proofs or ownership permissions. They contain
no completed target values; output handles come from the existing Bake layout.
"""
import numpy as np
from boundary_cell_ridge import D,B,symbols
from dominator_completion import freeze

NAMES=['has_output_ports','log_output_port_count','output_energy','output_rms','bounded_output_energy','has_direct_union','log_direct_union_count','direct_union_difference_energy']


def plan(source,rule,binding,ports,capacity):
    old=set(symbols(source));index={p:i for i,p in enumerate(ports)}
    new=np.zeros(capacity,np.float32)
    for p,i in index.items():new[i]=float(p not in old)
    env={slot:freeze(value) for slot,value in binding};pairs=[]
    for op in rule['effects']:
        if op['kind']=='copy':
            value=env.get(op['arg'].get('slot'));env.pop(op['dst'],None)
            if value is not None:env[op['dst']]=value
        else:
            if op['kind']=='union':
                operands=[env.get(a.get('slot')) for a in op['args']]
                if len(operands)==2 and all(v in index for v in operands):pairs.append(tuple(index[v] for v in operands))
            if 'dst' in op:env.pop(op['dst'],None)
    return new,pairs


def pack(plans):
    width=max(1,max(len(pairs) for _,pairs in plans));left=np.zeros((len(plans),width),np.int32);right=np.zeros_like(left);active=np.zeros_like(left,dtype=np.float32)
    for i,(_,pairs) in enumerate(plans):
        for j,(a,b) in enumerate(pairs):left[i,j]=a;right[i,j]=b;active[i,j]=1
    return np.array([new for new,_ in plans]),left,right,active


def evaluate(states,new,left,right,active,xp):
    channels=states[:,D:].reshape(len(states),-1,B)
    count=xp.sum(new,axis=1);nunion=xp.sum(active,axis=1)
    energy=xp.sum(xp.sum(channels*channels,axis=2)*new,axis=1)/(B*xp.maximum(count,1))
    delta=xp.take_along_axis(channels,left[:,:,None],axis=1)-xp.take_along_axis(channels,right[:,:,None],axis=1)
    union_energy=xp.sum(xp.sum(delta*delta,axis=2)*active,axis=1)/(B*xp.maximum(nunion,1))
    return xp.stack([(count>0).astype(xp.float32),xp.log1p(count),energy,xp.sqrt(xp.maximum(energy,0)),xp.tanh(4*energy),(nunion>0).astype(xp.float32),xp.log1p(nunion),union_energy],axis=1)
