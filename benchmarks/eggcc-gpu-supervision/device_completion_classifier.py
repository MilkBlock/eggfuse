"""Direct whole-state ridge -> complete token, without latent-output decoding."""
import numpy as np
from device_completion_readout import compile_state_layout
from device_completion_states import tokens


def load_head(archive,rid):
    keys=('mean','scale','coef','bias','feature_projection','feature_center')
    return {k:archive[f'head_{rid}_{k}'] for k in keys if f'head_{rid}_{k}' in archive}


def input_width(head):
    return head['feature_projection'].shape[0] if 'feature_projection' in head else head['coef'].shape[0]


def matmul_reference(x,w,xp):
    # CPU audit accumulates in f64 then rounds to f32. GPU remains native f32.
    return (x.astype(np.float64)@w.astype(np.float64)).astype(np.float32) if xp is np else x@w


def classifier_features(x,head,xp,reference=False):
    if "feature_projection" in head:
        if x.shape[1]!=head["feature_projection"].shape[0]:raise ValueError("normalized projection input width")
        z=x-head["feature_center"]
        projected=matmul_reference(z,head["feature_projection"],xp) if reference else z@head["feature_projection"]
        x=xp.concatenate([x,xp.tanh(projected)],axis=1)
    return x


def score_head(x,head,xp):
    normalized='feature_projection' in head
    x=classifier_features(x,head,xp,reference=normalized)
    z=(x-head['mean'])/head['scale']
    return (matmul_reference(z,head['coef'],xp) if normalized else z@head['coef'])+head['bias']


def choose(scores,required,states,xp):
    conflict=required.astype(xp.float32)@xp.swapaxes(1-states,-1,-2)
    index=xp.argmax(xp.where(conflict==0,scores,-float('inf')),axis=1)
    return index,states[index]


def compile_classifier(rule,head):
    p=compile_state_layout(rule);n=head['coef'].shape[0];k=len(p['states'])
    if head['coef'].shape!=(n,k) or any(head[key].shape!=(n,) for key in ('mean','scale')) or head['bias'].shape!=(k,):
        raise ValueError('classifier/layout dimensions')
    if ('feature_projection' in head)!=('feature_center' in head):raise ValueError('incomplete normalized projection')
    if 'feature_projection' in head:
        w=head['feature_projection'];center=head['feature_center']
        if w.ndim!=2 or min(w.shape)<1 or sum(w.shape)!=n or center.shape!=(w.shape[0],):raise ValueError('normalized projection dimensions')
    if any(not np.isfinite(v).all() for v in head.values()) or np.any(head['scale']<=0):raise ValueError('invalid classifier weights')
    return dict(p,head=head)


def apply(features,bindings,codes,scalar_ready,plan,xp):
    if features.shape[1]!=input_width(plan['head']):raise ValueError('classifier input width')
    scores=score_head(features,plan['head'],xp)
    edges=plan['edges'];left=edges[:,0];right=edges[:,1]
    roots=bindings['slot_roots'];valid=bindings['slot_valid']
    evidence=valid[:,left]&valid[:,right]&(roots[:,left]>=0)&(roots[:,right]>=0)&(roots[:,left]==roots[:,right])
    required=evidence.astype(xp.float32)@plan['incidence']>0
    finite=xp.all(xp.isfinite(features),axis=1)&xp.all(xp.isfinite(scores),axis=1)
    index,selected=choose(xp.where(finite[:,None],scores,0),required,plan['states'],xp)
    output=tokens(index,xp.where(scalar_ready[:,None,None],codes,0),plan['token'],xp)
    ready=finite&scalar_ready&xp.all(xp.isfinite(output),axis=1)
    return output,dict(ready=ready,chosen=index,scores=scores,required=required,selected=selected,
                       scalar_codes=codes,scalar_ready=scalar_ready)
