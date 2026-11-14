"""Decode semantic Eq proposals from floating Cell tokens and template requests.

No exact port identities or incidence matrix enter this readout. Its outputs
are proposals, not permission to mutate the graph. CPU labels come from exact
completed synthetic instances; only same-sort Eq port pairs are meaningful.
"""
import numpy as np
import mlx.core as mx
import mlx.nn as nn


def targets(rule,values,ref,width):
    a,b=np.triu_indices(width,1);labels=np.zeros(len(a),np.float32);mask=np.zeros(len(a),bool)
    for k,(i,j) in enumerate(zip(a,b)):
        if j>=len(rule['slots']):continue
        si,sj=rule['slots'][i]['sort'],rule['slots'][j]['sort']
        if si['kind']=='eq' and si==sj:
            mask[k]=True;labels[k]=ref.root(values[i])==ref.root(values[j])
    return dict(eq_target=labels,eq_mask=mask)


class EqReadout(nn.Module):
    def __init__(self,width,hidden=128):
        super().__init__()
        self.layers=nn.Sequential(nn.Linear(192,hidden),nn.GELU(),nn.Linear(hidden,hidden),nn.GELU(),nn.Linear(hidden,width*(width-1)//2))

    def __call__(self,tokens,requests):
        return self.layers(mx.concatenate([tokens,requests],axis=-1))


def masked_loss(logits,labels,mask):
    losses=nn.losses.binary_cross_entropy(logits,labels,reduction='none')
    return mx.sum(losses*mask)/mx.maximum(mx.sum(mask),1)


def metrics(logits,labels,mask,width):
    pred=np.asarray(logits)>=0;truth=np.asarray(labels)>0;mask=np.asarray(mask,bool)
    invalid=(~np.isfinite(np.asarray(logits))&mask).any(axis=1)
    fp=pred&~truth&mask;fn=~pred&truth&mask
    closed=pred.copy();a,b=np.triu_indices(width,1)
    for row in range(len(pred)):
        parent=list(range(width))
        def root(x):
            while parent[x]!=x:x=parent[x]
            return x
        for i,j,valid in zip(a,b,pred[row]&mask[row]):
            if valid:parent[root(int(i))]=root(int(j))
        closed[row]=[root(int(i))==root(int(j)) for i,j in zip(a,b)]
    cf=closed&~truth&mask;cn=~closed&truth&mask
    return dict(states=len(pred),pairs=int(mask.sum()),false_positive_pairs=int(fp.sum()),false_negative_pairs=int(fn.sum()),
                nonfinite_states=int(invalid.sum()),exact_states=int((~(fp|fn).any(axis=1)&~invalid).sum()),closed_false_positive_pairs=int(cf.sum()),
                closed_false_negative_pairs=int(cn.sum()),closed_exact_states=int((~(cf|cn).any(axis=1)&~invalid).sum()),
                states_with_false_merge=int(cf.any(axis=1).sum()))
