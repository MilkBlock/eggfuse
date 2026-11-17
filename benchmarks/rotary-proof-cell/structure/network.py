"""Same recurrent MLP family as the original, with an expanded structural ABI."""
import sys
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
sys.path.append(str(Path(__file__).resolve().parents[1]))
from model import rotate, address, rebase
from spec import DIM, INPUT_WIDTH, WIDTH, OFFSETS, SPECS, BOOL


def fields(logits):
    return {k:logits[...,a:b].reshape(logits.shape[:-1]+SPECS[k]) for k,(a,b) in OFFSETS.items()}

def discrete(logits):
    return {k:mx.stop_gradient((v>=0).astype(mx.int32) if k in BOOL else mx.argmax(v,-1)) for k,v in fields(logits).items()}

class StructureNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder=nn.Sequential(nn.Linear(INPUT_WIDTH,192),nn.GELU(),nn.Linear(192,DIM),nn.Tanh())
        self.transition_net=nn.Sequential(nn.Linear(DIM+3,256),nn.GELU(),nn.Linear(256,DIM),nn.Tanh())
        self.decoder=nn.Linear(DIM,WIDTH)

    def advance(self,token,position,phase,positions):
        h=rotate(token,position,'cell',True)
        step=mx.broadcast_to(mx.eye(3)[phase],(len(h),3))
        h=h+self.transition_net(mx.concatenate((h,step),axis=-1))
        logits=self.decoder(h);owner=discrete(logits)['owner'][:,0]
        position=mx.take_along_axis(positions,owner[:,None],axis=1)[:,0]
        return rotate(h,position,'cell'),position,logits,owner

    def rollout(self,seed,positions,read=True,poison=False):
        token=rotate(self.encoder(seed),positions[:,0],'cell');position=positions[:,0]
        tokens=[];locations=[];logits=[];owners=[]
        for stage in range(3):
            token,position,score,owner=self.advance(token,position,stage,positions)
            tokens.append(token);locations.append(position);logits.append(score);owners.append(owner)
        result=dict(tokens=mx.stack(tokens),locations=mx.stack(locations),logits=mx.stack(logits),owners=mx.stack(owners))
        if read:result.update(self.read_old(tokens[-1],locations[-1],owners[-1],tokens[-2],positions,poison))
        return result

    def read_old(self,final,where,owner,old,positions,poison=False):
        current=discrete(self.decoder(rotate(final,where,'cell',True)))
        retired=current['retired'][:,0]!=0
        if poison:old=mx.full_like(old,float('nan'))
        current_a=mx.where((owner==1)[:,None],final,old)
        active=mx.stack((~retired,owner==2),axis=1)
        bank=mx.where(active[...,None],mx.stack((current_a,final),axis=1),0)
        index=mx.clip(owner-1,0,1)
        selected=mx.take_along_axis(bank,index[:,None,None],axis=1)[:,0]
        at=mx.take_along_axis(positions[:,1:3],index[:,None],axis=1)[:,0]
        header=discrete(self.decoder(rotate(selected,at,'cell',True)))
        ports=mx.broadcast_to(mx.arange(8),(len(final),8));keys=address(positions[:,1,None],ports)
        picked=mx.stop_gradient(mx.argmax(keys@mx.swapaxes(address(positions[:,1,None],ports),-1,-2),-1))
        mapped=mx.take_along_axis(header['alias'],picked,axis=1)
        translated=rebase(keys,positions[:,1,None],picked,at[:,None],mapped)
        target=address(at[:,None],mx.broadcast_to(mx.arange(9),(len(final),9)))
        resolved=mx.stop_gradient(mx.argmax(translated@mx.swapaxes(target,-1,-2),-1))
        return dict(read_roles=mx.take_along_axis(header['layout'],resolved,axis=1),read_ports=resolved,
            read_payload=header['payload'],read_eq=header['eq'],
            read_valid=mx.take_along_axis(active,index[:,None],axis=1)[:,0]&(owner>0)&mx.all(mapped<9,axis=1),
            old_active=active[:,0],old_visible=mx.sum(mx.abs(bank[:,0]),axis=1))


def loss(model,seed,positions,truth):
    result=model.rollout(seed,positions,read=False)
    total=mx.array(0.)
    for k,value in fields(result['logits']).items():
        if k in BOOL:part=nn.losses.binary_cross_entropy(value,truth[k].astype(mx.float32),reduction='mean')
        else:part=nn.losses.cross_entropy(value.reshape(-1,value.shape[-1]),truth[k].reshape(-1),reduction='mean')
        total=total+({'eq':4,'layout':2,'alias':2}.get(k,1))*part
    return total
