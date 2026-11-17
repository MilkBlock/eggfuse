"""CPU-only soft-claim diagnostics and raw output binding checks."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from data import N,K,V,Q,truth


def probabilities(x):
    e=np.exp(x.astype(np.float64)-x.max(axis=-1,keepdims=True));return e/e.sum(axis=-1,keepdims=True)


def soft_metrics(a,b,out):
    active=probabilities(out['active_logits'])[...,1];p=probabilities(out['pointer_logits'])
    claims=(active[...,None,None]*p[:,:,0,:,None]*p[:,:,1,None,:]).sum(1)
    target=a[:,:,0,None]==b[:,None,:,0];count=target.sum((1,2));valid=out['active'].sum(1)
    entropy=-(active*np.log(np.maximum(active,1e-30))+(1-active)*np.log(np.maximum(1-active,1e-30)))
    return dict(soft_coverage_mse=float((((claims-target)**2).sum((1,2))/np.maximum(count,1)).mean()),
        soft_count_mse=float(((active.sum(1)-count)**2).mean()/Q),active_entropy=float(entropy.mean()),
        hard_count_absolute_error=float(np.abs(valid-count).mean()))


def check_decode(out,sp):
    p=out['pointer_logits'].argmax(-1);f=out['field_logits'];fields=np.stack((f[...,:K].argmax(-1),f[...,K:K+V].argmax(-1),f[...,K+V:].argmax(-1)),-1)
    np.testing.assert_array_equal(out['active'],out['active_logits'].argmax(-1));np.testing.assert_array_equal(out['pointers'],p)
    np.testing.assert_array_equal(out['fields'],fields);np.testing.assert_array_equal(out['addresses'],np.stack((sp[p[...,0]],sp[N+p[...,1]]),-2))
    assert all(np.isfinite(out[k]).all() for k in ('active_logits','pointer_logits','field_logits'))
