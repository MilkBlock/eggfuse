"""Shared learned relation/pointer functions, with explicit GPU dataflow features.

No teacher, source executor, shape catalog or layout oracle is called here.
The learned heads operate on anonymous local relation features, not port IDs.
"""
import mlx.core as mx
import mlx.nn as nn
from abi import *
from model import rotate,address,rebase

EPS=1e-6

def parts(seed):
    return {k:seed[...,a:b].reshape(seed.shape[:-1]+shape) for k,(a,b,shape) in PARTS.items()}

def catlog(p):return mx.log(mx.maximum(p,EPS))
def bitlog(p):return mx.log(mx.maximum(p,EPS))-mx.log(mx.maximum(1-p,EPS))
def onehot(i,n):return mx.eye(n)[mx.stop_gradient(i)]

def unpack(h):
    return h[:,:EQ_END].reshape(-1,8,8),h[:,EQ_END:PTR_END].reshape(-1,8,9),h[:,PTR_END:SEED_END],h[:,SEED_END:PHASE_END],h[:,-1:]

def pack(eq,ptr,seed,phase,gate):
    return mx.concatenate((eq.reshape(-1,64),ptr.reshape(-1,72),seed,phase,gate),-1)


def decode_local(h):
    eq,ptr,seed,phase,gate=unpack(h);d=parts(seed);n=len(h)
    phase_id=mx.stop_gradient(mx.argmax(phase,-1));stage1=phase_id==0;stage2=phase_id==1
    transfer=(gate[:,0]>.5)&(phase_id==2);on=d['on'][:,0]>.5
    # The trusted certificate macro is instantiated from protected inputs and
    # generated choices. It does not repair equality or the pointer distribution.
    proof=mx.where(stage1,0,mx.where(stage2,mx.where(on,1,2),mx.where(transfer,3,4)))
    refs=mx.stack((mx.where(stage1,0,mx.where(stage2,mx.where(on,1,2),0)),
                   mx.where(stage1,4,mx.where(stage2,mx.where(on,2,4),2)),
                   mx.where((phase_id==2)&transfer,3,4)),-1)
    uw=mx.concatenate((d['union'],mx.zeros((n,2,2))),-1)
    uw=mx.where((stage2&on)[:,None,None],uw,mx.broadcast_to(onehot(mx.array(9),10),(n,2,10)))
    alias=mx.concatenate((ptr,mx.zeros((n,8,1))),-1)
    new=gate[:,None,:]*onehot(mx.array(4),9)[None,:,None]
    empty=(1-gate[:,None,:])*onehot(mx.array(8),9)[None,:,None]
    layout=mx.concatenate((mx.swapaxes(ptr,-1,-2),new,empty),-1)
    values=dict(ops=catlog(d['ops']),args=catlog(d['args']),layout=catlog(layout),alias=catlog(alias),
        eq=bitlog(mx.stack([eq[:,i,j] for i,j in PAIRS],-1)),
        owner=catlog(onehot(mx.where(transfer,2,1),3)[:,None,:]),proof=catlog(onehot(proof,5)[:,None,:]),
        premises=catlog(onehot(refs,5)),union_witness=catlog(uw),
        gate=catlog(mx.concatenate((d['query'],mx.zeros((n,2,2))),-1)),commands=catlog(d['commands']),
        payload=bitlog(d['payload']),pending=bitlog(mx.stack((stage1&on,~transfer),-1).astype(mx.float32)),
        retired=bitlog(transfer[:,None].astype(mx.float32)))
    return mx.concatenate([values[k].reshape(n,-1) for k in SPECS],-1)


def discrete(scores):
    out={}
    for k,(a,b) in OFFSETS.items():
        v=scores[...,a:b].reshape(scores.shape[:-1]+SPECS[k])
        out[k]=mx.stop_gradient((v>=0).astype(mx.int32) if k in BOOL else mx.argmax(v,-1))
    return out


class SharedNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.relation=nn.Sequential(nn.Linear(8,32),nn.Tanh(),nn.Linear(32,1))
        self.pointer=nn.Sequential(nn.Linear(8,32),nn.Tanh(),nn.Linear(32,1))
        self.activation=nn.Sequential(nn.Linear(1,8),nn.Tanh(),nn.Linear(8,1))

    def relation_features(self,eq,d,allow_union):
        n=len(eq)
        # Select argument relations from the previously GENERATED relation state.
        args=d['args'][:,:,:,:8]
        a=mx.concatenate((mx.zeros((n,4,8)),args[:,:,0]),axis=1)
        b=mx.concatenate((mx.zeros((n,4,8)),args[:,:,1]),axis=1)
        ea=a@eq@mx.swapaxes(a,-1,-2);eb=b@eq@mx.swapaxes(b,-1,-2)
        op=mx.concatenate((mx.zeros((n,4,2)),d['ops']),axis=1)
        same=op@mx.swapaxes(op,-1,-2)
        unary=op[:,:,0,None]*op[:,None,:,0]
        u,v=d['union'][:,0],d['union'][:,1]
        direct=(u[:,:,None]*v[:,None,:]+v[:,:,None]*u[:,None,:])*d['on'][:,:,None]*allow_union
        via=mx.max(eq[:,:,:,None]*eq[:,None,:,:],axis=2)
        identity=mx.broadcast_to(mx.eye(8),(n,8,8))
        return mx.stack((eq,identity,direct,same,unary,ea,eb,via),-1)

    def closure(self,eq,d,allow_union):
        # Fixed bounded rollout, NOT an exact closure loop. New relation votes
        # always come from the same learned scorer at every pair and micro-step.
        for _ in range(8):
            score=self.relation(self.relation_features(eq,d,allow_union))[...,0]
            eq=mx.maximum(eq,mx.sigmoid(score))
        return eq

    def pointer_matrix(self,command,insertion=False):
        n=len(command);src=mx.arange(8)[None,:,None];dst=mx.arange(9 if insertion else 8)[None,None,:]
        k=command[:,None,None];shape=(n,8,9 if insertion else 8)
        f=[src==dst,dst==src+1,dst==src-1,src==k,src==k+1,(src>=4)&insertion,
           mx.full(shape,float(insertion)),mx.full(shape,float(not insertion))]
        features=mx.stack([mx.broadcast_to(v,shape).astype(mx.float32) for v in f],-1)
        return mx.softmax(self.pointer(features)[...,0],axis=-1)

    def encode(self,seed,positions):
        n=len(seed)
        h=pack(mx.broadcast_to(mx.eye(8),(n,8,8)),mx.broadcast_to(mx.eye(8,9),(n,8,9)),seed,
               mx.zeros((n,3)),mx.zeros((n,1)))
        return rotate(h,positions[:,0],'cell')

    def advance(self,token,where,phase,positions):
        h=rotate(token,where,'cell',True);eq,ptr,seed,_,old_gate=unpack(h);d=parts(seed);n=len(h)
        if phase<2:
            eq=self.closure(eq,d,float(phase==1));gate=mx.zeros((n,1))
        else:
            query=d['query'];qeq=(query[:,0,None,:]@eq@query[:,1,:,None])[:,0,:]
            gate=mx.sigmoid(self.activation(qeq))
            commands=mx.stop_gradient(mx.argmax(d['commands'],-1))
            # Compose learned primitive pointer distributions, never oracle maps.
            proposal=ptr[:,:,:8]@self.pointer_matrix(commands[:,0])@self.pointer_matrix(commands[:,1])
            proposal=proposal@self.pointer_matrix(mx.zeros((n,),mx.int32),True)
            ptr=gate[:,:,None]*proposal+(1-gate[:,:,None])*ptr
        local=pack(eq,ptr,seed,mx.broadcast_to(onehot(mx.array(phase),3),(n,3)),gate)
        scores=decode_local(local);owner=discrete(scores)['owner'][:,0]
        at=mx.take_along_axis(positions,owner[:,None],axis=1)[:,0]
        return rotate(local,at,'cell'),at,scores,owner

    def rollout(self,seed,positions,read=True):
        token=self.encode(seed,positions);at=positions[:,0]
        tokens=[];locations=[];logits=[];owners=[]
        for phase in range(3):
            token,at,score,owner=self.advance(token,at,phase,positions)
            tokens.append(token);locations.append(at);logits.append(score);owners.append(owner)
        out=dict(tokens=mx.stack(tokens),locations=mx.stack(locations),logits=mx.stack(logits),owners=mx.stack(owners))
        if read:out.update(self.read_old(tokens[-1],locations[-1],owners[-1],tokens[-2],positions))
        return out

    def read_old(self,final,at,owner,old,positions,poison=False):
        header=discrete(decode_local(rotate(final,at,'cell',True)));retired=header['retired'][:,0]!=0
        if poison:old=mx.full_like(old,float('nan'))
        active=mx.stack((~retired,owner==2),1)
        bank=mx.stack((mx.where((owner==1)[:,None],final,old),final),1)
        bank=mx.where(active[...,None],bank,0);index=mx.clip(owner-1,0,1)
        token=mx.take_along_axis(bank,index[:,None,None],axis=1)[:,0]
        where=mx.take_along_axis(positions[:,1:3],index[:,None],axis=1)[:,0]
        header=discrete(decode_local(rotate(token,where,'cell',True)))
        ports=mx.broadcast_to(mx.arange(8),(len(final),8));keys=address(positions[:,1,None],ports)
        mapped=header['alias'];translated=rebase(keys,positions[:,1,None],ports,where[:,None],mapped)
        targets=address(where[:,None],mx.broadcast_to(mx.arange(9),(len(final),9)))
        resolved=mx.stop_gradient(mx.argmax(translated@mx.swapaxes(targets,-1,-2),-1))
        return dict(read_roles=mx.take_along_axis(header['layout'],resolved,axis=1),read_ports=resolved,
            read_payload=header['payload'],read_eq=header['eq'],
            read_valid=mx.take_along_axis(active,index[:,None],axis=1)[:,0]&(owner>0)&mx.all(mapped<9,axis=1),
            old_active=active[:,0],old_visible=mx.sum(mx.abs(bank[:,0]),-1))


def loss(model,seed,positions,truth):
    result=model.rollout(seed,positions,False);scores=result['logits'];total=mx.array(0.)
    for k in ('eq','alias','layout'):
        a,b=OFFSETS[k];value=scores[...,a:b].reshape(scores.shape[:-1]+SPECS[k])
        if k=='eq':part=nn.losses.binary_cross_entropy(value,truth[k].astype(mx.float32),reduction='mean')
        else:part=nn.losses.cross_entropy(value.reshape(-1,value.shape[-1]),truth[k].reshape(-1),reduction='mean')
        total=total+({'eq':4,'alias':2,'layout':2}[k])*part
    # Activation has its own differentiable output; discrete certificate fields
    # do not leak teacher decisions into recurrence or routing.
    gate=result['tokens'][2,:,-1:]
    total=total+nn.losses.binary_cross_entropy(bitlog(gate),truth['retired'][2].astype(mx.float32),reduction='mean')
    return total
