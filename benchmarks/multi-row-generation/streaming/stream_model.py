"""Causal row sequences, directly consuming generated latent and own symbols."""
import sys
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from data import K,V,N,Q,FEATURES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import DIM,Attention

TOKEN_WIDTH=DIM+2+2*N+K+2*V


def hard_symbol(logits):
    soft=mx.softmax(logits,-1);hard=mx.eye(logits.shape[-1])[mx.stop_gradient(mx.argmax(logits,-1))]
    return mx.stop_gradient(hard)+(soft-mx.stop_gradient(soft))


def token(latent,active,pointer,fields):
    return mx.concatenate((latent,hard_symbol(active),hard_symbol(pointer[:,:,0]),hard_symbol(pointer[:,:,1]),
        hard_symbol(fields[...,:K]),hard_symbol(fields[...,K:K+V]),hard_symbol(fields[...,K+V:])),axis=-1)


class StreamBlock(nn.Module):
    def __init__(self):
        super().__init__();self.norm=nn.LayerNorm(DIM);self.current=Attention();self.source=Attention();self.history=Attention()
        self.ff=nn.Sequential(nn.Linear(DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,DIM))
    def __call__(self,q,pos,source_kv,history_kv,history_mask):
        _,z=self.current(self.norm(q),self.norm(q),pos,pos);q=q+z
        _,z=self.source.from_prepared(self.norm(q),pos,source_kv);q=q+z
        if history_kv is not None:
            _,z=self.history.from_prepared(self.norm(q),pos,history_kv,history_mask);q=q+z
        return q+self.ff(self.norm(q))


class StreamGenerator(nn.Module):
    def __init__(self,arm='feedback'):
        super().__init__();self.arm=arm;self.encoder=nn.Sequential(nn.Linear(FEATURES,DIM),nn.GELU(),nn.Linear(DIM,DIM))
        self.row=nn.Embedding(4,DIM);self.position=nn.Embedding(4,DIM);self.blocks=[StreamBlock() for _ in range(3)]
        self.history_encoder=nn.Linear(TOKEN_WIDTH,DIM);self.norm=nn.LayerNorm(DIM);self.left=Attention();self.right=Attention()
        self.active=nn.Linear(DIM,2);self.fields=nn.Sequential(nn.Linear(DIM,2*DIM),nn.GELU(),nn.Linear(2*DIM,K+2*V))
    def __call__(self,x,sp,op,rows,length,intervention='none'):
        if rows*length!=Q:raise ValueError('exactly eight output slots')
        source=self.encoder(x);source_kv=[b.source.prepare_memory(source,sp) for b in self.blocks]
        left_kv=self.left.prepare_memory(source[:,:N],sp[:N]);right_kv=self.right.prepare_memory(source[:,N:],sp[N:])
        history=[None]*len(self.blocks);history_pos=None;parts=[];order=[]
        for t in range(length):
            indices=[r*length+t for r in range(rows)];ids=mx.array(indices,mx.int32);pos=op[ids]
            q=self.row(pos[:,0])+self.position(mx.full((rows,),t,mx.int32));q=mx.broadcast_to(q,(x.shape[0],rows,DIM))
            mask=None
            if history_pos is not None and intervention=='local':mask=pos[:,0,None]==history_pos[None,:,0]
            for index,block in enumerate(self.blocks):q=block(q,pos,source_kv[index],history[index],mask)
            h=self.norm(q);left,_=self.left.from_prepared(h,pos,left_kv);right,_=self.right.from_prepared(h,pos,right_kv)
            pointer=mx.stack((left,right),2);active=self.active(h);fields=self.fields(h);emitted=token(h,active,pointer,fields)
            parts.append(dict(latent=h,active_logits=active,pointer_logits=pointer,field_logits=fields,token=emitted));order.extend(indices)
            if t+1<length:
                payload=mx.zeros_like(emitted) if self.arm=='blind' or intervention=='erase' else emitted
                encoded=self.history_encoder(payload)
                for index,block in enumerate(self.blocks):
                    new=block.history.prepare_memory(block.norm(encoded),pos)
                    history[index]=new if history[index] is None else tuple(mx.concatenate((a,b),axis=-2) for a,b in zip(history[index],new))
                history_pos=pos if history_pos is None else mx.concatenate((history_pos,pos),axis=0)
        inverse=mx.array(np.argsort(order).astype(np.int32))
        return {k:mx.concatenate([p[k] for p in parts],axis=1)[:,inverse] for k in parts[0]}
