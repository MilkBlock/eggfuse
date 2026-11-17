"""Unanchored set decoder: no source anchor, target assignment or repair in forward."""
import sys
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
from data import N,K,V,Q,FEATURES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import Attention,DIM


class Block(nn.Module):
    def __init__(self):
        super().__init__();self.norm=nn.LayerNorm(DIM);self.self_attn=Attention();self.cross=Attention()
        self.ff=nn.Sequential(nn.Linear(DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,DIM))
    def __call__(self,q,m,qp,mp,mask):
        _,z=self.self_attn(self.norm(q),self.norm(q),qp,qp,mask);q=q+z
        _,z=self.cross(self.norm(q),m,qp,mp);q=q+z
        return q+self.ff(self.norm(q))


class SetGenerator(nn.Module):
    def __init__(self,mode='joint'):
        super().__init__();self.mode=mode;self.encoder=nn.Sequential(nn.Linear(FEATURES,DIM),nn.GELU(),nn.Linear(DIM,DIM))
        self.row=nn.Embedding(4,DIM);self.position=nn.Embedding(4,DIM);self.blocks=[Block() for _ in range(3)]
        self.norm=nn.LayerNorm(DIM);self.left=Attention();self.right=Attention();self.active=nn.Linear(DIM,2)
        self.fields=nn.Sequential(nn.Linear(DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,K+2*V))
    def __call__(self,x,source_pos,output_pos,cut_cross_row=False):
        memory=self.encoder(x);local_position=source_pos[:,1]
        q=self.row(output_pos[:,0])+self.position(local_position)
        q=mx.broadcast_to(q,(x.shape[0],Q,DIM))
        mask=None
        if self.mode=='independent' or cut_cross_row:mask=output_pos[:,0,None]==output_pos[None,:,0]
        for layer in self.blocks:q=layer(q,memory,output_pos,source_pos,mask)
        h=self.norm(q);left,_=self.left(h,memory[:,:N],output_pos,source_pos[:N]);right,_=self.right(h,memory[:,N:],output_pos,source_pos[N:])
        return dict(active_logits=self.active(h),pointer_logits=mx.stack((left,right),2),field_logits=self.fields(h),latent=h)


def decode(out,source_pos):
    pointers=mx.argmax(out['pointer_logits'],-1);active=mx.argmax(out['active_logits'],-1)
    scores=out['field_logits'];fields=mx.stack((mx.argmax(scores[...,:K],-1),mx.argmax(scores[...,K:K+V],-1),mx.argmax(scores[...,K+V:],-1)),-1)
    addresses=mx.stack((source_pos[pointers[...,0]],source_pos[N+pointers[...,1]]),-2)
    return dict(active=active,pointers=pointers,fields=fields,addresses=addresses)


def loss(model,x,sp,op,target):
    out=model(x,sp,op);active=target[...,0];value=nn.losses.cross_entropy(out['active_logits'],active,reduction='mean')
    for col in range(2):value+=mx.mean(active*nn.losses.cross_entropy(out['pointer_logits'][:,:,col,:],target[...,col+1],reduction='none'))
    offset=0
    for col,width in enumerate((K,V,V)):
        value+=mx.mean(active*nn.losses.cross_entropy(out['field_logits'][...,offset:offset+width],target[...,col+3],reduction='none'));offset+=width
    return value


def assignment_cost(out,target):
    def nll(logits,labels):
        lp=mx.logsumexp(logits,-1,keepdims=True)-logits
        return mx.take_along_axis(mx.broadcast_to(lp[:,:,None,:],(lp.shape[0],Q,Q,lp.shape[-1])),mx.broadcast_to(labels[:,None,:,None],(lp.shape[0],Q,Q,1)),-1)[...,0]
    active=target[...,0];cost=nll(out['active_logits'],active)
    for col in range(2):cost+=active[:,None,:]*nll(out['pointer_logits'][:,:,col,:],target[...,col+1])
    offset=0
    for col,width in enumerate((K,V,V)):
        cost+=active[:,None,:]*nll(out['field_logits'][...,offset:offset+width],target[...,col+3]);offset+=width
    return cost


def verify(a,b,out):
    # Read-only GPU equality-join verification; never feeds the generator.
    active=out['active'];i=out['pointers'][...,0];j=out['pointers'][...,1]
    produced=mx.sum(active[...,None,None]*mx.eye(N)[i][...,None]*mx.eye(N)[j][...,None,:],axis=1)
    expected=a[:,:,0,None]==b[:,None,:,0]
    aa=mx.take_along_axis(a,i[...,None],axis=1);bb=mx.take_along_axis(b,j[...,None],axis=1)
    want=mx.stack((aa[...,0],aa[...,1],bb[...,1]),-1)
    return mx.all(produced==expected,axis=(1,2))&mx.all((out['fields']==want)|(~active.astype(mx.bool_)[...,None]),axis=(1,2))
