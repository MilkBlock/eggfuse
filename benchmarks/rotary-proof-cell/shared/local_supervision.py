"""OFFLINE rule-local supervision. Never imported by the inference network.

These labels encode the declared primitive rules, not any held-out Cell shape or
whole transfer permutation. Runtime still executes learned MLPs, not this table.
"""
from itertools import product
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from shared_net import bitlog

FEATURES=np.array(list(product((0.,1.),repeat=8)),np.float32)
f=FEATURES.astype(bool)
RELATION_LABEL=(f[:,0]|f[:,1]|f[:,2]|f[:,7]|(f[:,3]&f[:,5]&(f[:,4]|f[:,6]))).astype(np.float32)
# Only the seven single adjacent swaps present in the original training corpus.
SWAP_LABEL=np.array([[k+1 if s==k else k if s==k+1 else s for s in range(8)] for k in range(7)],np.int32)
INSERT_LABEL=np.array([[s+int(s>=4) for s in range(8)]],np.int32)


def local_loss(model):
    score=model.relation(mx.array(FEATURES))[:,0];truth=mx.array(RELATION_LABEL)
    bce=nn.losses.binary_cross_entropy(score,truth,reduction='none')
    relation=mx.mean(bce*mx.where(truth>0,1.,16.))
    swap=model.pointer_matrix(mx.arange(7));insert=model.pointer_matrix(mx.zeros((1,),mx.int32),True)
    pointer=-mx.mean(mx.log(mx.maximum(mx.take_along_axis(swap,mx.array(SWAP_LABEL)[...,None],axis=-1),1e-6)))
    pointer-=mx.mean(mx.log(mx.maximum(mx.take_along_axis(insert,mx.array(INSERT_LABEL)[...,None],axis=-1),1e-6)))
    activation=nn.losses.binary_cross_entropy(model.activation(mx.array([[0.],[1.]]))[:,0],mx.array([0.,1.]),reduction='mean')
    return relation+pointer+activation
