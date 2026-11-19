"""A causal PyTorch proposal from observed raw events; no source joins in forward."""
import torch
from torch import nn

KEYS=4
WIDTH=32


class ReadyPolicy(nn.Module):
    def __init__(self,arm):
        super().__init__()
        if arm not in ('keyed','blind'):raise ValueError(arm)
        self.arm=arm
        self.query=nn.Sequential(nn.Linear(7,WIDTH),nn.Tanh(),nn.Linear(WIDTH,WIDTH))
        self.event=nn.Sequential(nn.Linear(16,WIDTH),nn.Tanh(),nn.Linear(WIDTH,WIDTH))
        self.read=nn.Sequential(nn.Linear(7,WIDTH),nn.Tanh(),nn.Linear(WIDTH,2))
        self.register_buffer('key_symbols',torch.arange(4),persistent=False)
        self.register_buffer('kind_symbols',torch.arange(4),persistent=False)
        self.register_buffer('value_symbols',torch.arange(8),persistent=False)
        self.register_buffer('query_features',torch.cat((
            torch.eye(4)[:,None,:].expand(4,3,4),torch.eye(3)[None,:,:].expand(4,3,3)),-1).reshape(12,7),persistent=False)
        self.register_buffer('ticks',torch.eye(4),persistent=False)

    def new_stream(self):
        return OnlinePolicy(self)


class OnlinePolicy:
    """Per-stream state. Only the current raw wave enters each step."""
    def __init__(self,model):
        self.model=model
        self.evidence=None
        self.expected_tick=0
        self.q=model.query(model.query_features)

    def scores(self,tick,wave):
        if tick!=self.expected_tick or not 0<=tick<4 or ((wave is None)!=(tick==3)):
            raise ValueError('expected three ordered raw waves followed by a separate finish tick')
        self.expected_tick+=1
        m=self.model
        if wave is not None:
            kind,key,value=wave.unbind(-1)
            key_features=(key[...,None]==m.key_symbols).float()
            if m.arm=='blind':key_features=torch.zeros_like(key_features)
            features=torch.cat(((kind[...,None]==m.kind_symbols).float(),key_features,
                                (value[...,None]==m.value_symbols).float()),-1)
            scores=(self.q @ m.event(features).transpose(-1,-2)) / WIDTH**0.5
            masked=torch.where(kind[:,None,:]!=0,scores.sigmoid(),0.)
            current=masked.amax(-1).unflatten(-1,(KEYS,3))
            self.evidence=current if self.evidence is None else torch.maximum(self.evidence,current)
        phase=m.ticks[tick].expand(len(self.evidence),KEYS,4)
        return m.read(torch.cat((self.evidence,phase),-1)).transpose(1,2)

    def __call__(self,tick,wave):
        return self.scores(tick,wave)>=0
