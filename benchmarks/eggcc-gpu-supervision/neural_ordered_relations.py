"""Ordered query-interface incidence, separate from dense learned Cell tokens.

Bake supplies the required slot sharing. Runtime identity handles supply actual
incidence, not a CPU match result. Both matrices are given to a learned head;
this module does not reduce them to a match decision.
"""
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from neural_cell_transition import CellTransition


def demand(rule, atoms, width):
    slots=np.full((atoms,width),-1,np.int32)
    for ai,atom in enumerate(rule['query']):
        if len(atom['args'])>width: raise ValueError('query projection capacity')
        for fi,arg in enumerate(atom['args']): slots[ai,fi]=arg['slot']
    slots=slots.reshape(-1)
    return ((slots[:,None]>=0)&(slots[None,:]>=0)&(slots[:,None]==slots[None,:])).astype(np.float32)


def incidence(labels, required, xp=np):
    # labels: batch x atoms x projected fields; -1 means inactive/padding.
    flat=labels.reshape(labels.shape[0],-1)
    actual=(flat[:,:,None]>=0)&(flat[:,None,:]>=0)&(flat[:,:,None]==flat[:,None,:])
    req=xp.broadcast_to(required,actual.shape)
    return xp.concatenate([actual.astype(xp.float32).reshape(len(labels),-1),req.reshape(len(labels),-1)],axis=1)


def projected(rule, rows, atoms, width):
    labels=np.full((1,atoms,width),-1,np.int32)
    for ai,row in enumerate(rows):labels[0,ai,:len(row)]=row
    return incidence(labels,demand(rule,atoms,width))[0]


class OrderedCellTransition(CellTransition):
    def __init__(self,input_width,relation_width,hidden=128):
        super().__init__(input_width,hidden)
        self.relation=nn.Sequential(nn.Linear(relation_width,hidden),nn.GELU(),nn.Linear(hidden,hidden),nn.GELU())
        self.match_relation=nn.Linear(hidden,1)
        self.token_relation=nn.Linear(hidden,128)
        # Preserve the parent model before any updates; learn corrections jointly.
        self.match_relation.weight=mx.zeros_like(self.match_relation.weight)
        self.match_relation.bias=mx.zeros_like(self.match_relation.bias)
        self.token_relation.weight=mx.zeros_like(self.token_relation.weight)
        self.token_relation.bias=mx.zeros_like(self.token_relation.bias)

    def __call__(self,x,edges,mask,request,relations):
        return self.transition(self.encode(x),edges,mask,request,relations)

    def transition(self,source_tokens,edges,mask,request,relations):
        logits,token=super().transition(source_tokens,edges,mask,request)
        h=self.relation(relations)
        return self.match_logit(logits,h),token+self.token_relation(h)

    def match_logit(self,logits,h):
        return logits+self.match_relation(h)[:,0]


class InterfaceCellTransition(OrderedCellTransition):
    """Slot-only constructor matching is independent of latent source content.

    Scalar predicates and other query semantics require additional explicit
    inputs; this specialization is not a general-query correctness claim.
    """
    def match_logit(self,logits,h):
        return self.match_relation(h)[:,0]


class EdgeResidualCellTransition(InterfaceCellTransition):
    """Template-ordered floating edges bypass attention pooling.

    No semantic IDs are inputs. Zero initialization preserves the parent model;
    training can retain relations suppressed by attention in a dense projection.
    """
    def __init__(self,input_width,relation_width,hidden=128):
        import math
        fields=input_width//128;ports=math.isqrt(relation_width//2)
        if input_width%128 or fields<1 or 2*ports*ports!=relation_width or ports%fields:
            raise ValueError('edge residual needs a rectangular compiled interface')
        super().__init__(input_width,relation_width,hidden)
        self.atoms=ports//fields
        self.edge_residual=nn.Linear(self.atoms*self.atoms*64,128,bias=False)
        self.edge_residual.weight=mx.zeros_like(self.edge_residual.weight)

    def transition(self,source_tokens,edges,mask,request,relations):
        logits,token=super().transition(source_tokens,edges,mask,request,relations)
        if edges.shape[1:]!=(self.atoms,self.atoms,64):raise ValueError('edge residual layout mismatch')
        valid=mask[:,:,None]&mask[:,None,:]
        features=mx.where(valid[...,None],edges,0).reshape(len(edges),-1)
        return logits,token+self.edge_residual(features)


def ordered_model(input_width,relation_width,interface_only=False,edge_residual=False):
    if edge_residual:
        if not interface_only:raise ValueError('edge residual currently requires interface-only matching')
        return EdgeResidualCellTransition(input_width,relation_width)
    cls=InterfaceCellTransition if interface_only else OrderedCellTransition
    return cls(input_width,relation_width)
