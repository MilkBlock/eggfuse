"""NumPy-only source semantics and actual-token audit; no model execution."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import KEYS,VALUES

def decode(logits):
    cols=[];at=0
    for width in (KEYS,KEYS,VALUES,VALUES):cols.append(logits[...,at:at+width].argmax(-1));at+=width
    return np.stack(cols,-1)


def reference(a,b,rounds):
    """Independent source-edge path composition; never part of neural forward."""
    batch,n=a.shape[:2];all_ptr=[];all_fields=[]
    for g in range(batch):
        lookup={int(row[0]):j for j,row in enumerate(b[g])}
        p=np.array([lookup[int(row[0])] for row in a[g]],np.int32)
        f=np.stack((a[g,:,0],b[g,p,1],a[g,:,1],b[g,p,2]),-1)
        ps=[p];fs=[f]
        for _ in range(1,rounds):
            lookup={int(row[0]):j for j,row in enumerate(f)}
            p=np.array([lookup[int(row[1])] for row in f],np.int32)
            f=np.stack((f[:,0],f[p,1],f[:,2],f[p,3]),-1)
            ps.append(p);fs.append(f)
        all_ptr.append(ps);all_fields.append(fs)
    return np.array(all_ptr).transpose(1,0,2),np.array(all_fields).transpose(1,0,2,3)


def audit(a,b,pa,pb,pp,length,out,weight,bias,typed=False):
    rounds=len(out['latent']);ptr,truth=reference(a,b,rounds)
    decoded=decode(out['latent'].astype(np.float64)@weight.astype(np.float64).T+bias.astype(np.float64))
    advertised=decode(out['field_logits']);binding=(decoded==advertised).all(axis=(2,3))
    pointer=(out['pointers']==ptr).all(-1);values=(decoded==truth).all(axis=(2,3));addresses=[]
    for step in range(rounds):
        positions=pb if step==0 else pa+np.array([0,(step+1)*length],np.int32)
        addresses.append((out['addresses'][step]==positions[ptr[step]]).all(axis=(1,2)))
    finite=np.isfinite(out['latent']).all(axis=(2,3))&np.isfinite(out['field_logits']).all(axis=(2,3))&np.isfinite(out['pointer_logits']).all(axis=(2,3))
    format_ok=np.ones_like(finite)
    if typed:
        token=out['latent'];at=0
        for width in (KEYS,KEYS,VALUES,VALUES):
            part=token[...,at:at+width]
            format_ok &= np.all((part==0)|(part==1),axis=(2,3)) & np.all(part.sum(-1)==1,axis=2)
            at+=width
        format_ok &= np.all(token[...,at:]==0,axis=(2,3))
    legal=pointer&values&binding&np.array(addresses)&finite&format_ok
    cumulative=np.logical_and.accumulate(legal,axis=0)
    return dict(graphs=len(a),rounds=rounds,all_finite=bool(finite.all()),typed_format_valid=bool(format_ok.all()) if typed else None,round_exact_graphs=legal.sum(1).tolist(),
        cumulative_exact_graphs=cumulative.sum(1).tolist(),pointer_exact_graphs=pointer.sum(1).tolist(),
        field_exact_graphs=values.sum(1).tolist(),readout_binding_agrees=bool(binding.all()),
        first_failing_round=[int(np.flatnonzero(~cumulative[:,g])[0])+1 if not cumulative[-1,g] else None for g in range(len(a))])
