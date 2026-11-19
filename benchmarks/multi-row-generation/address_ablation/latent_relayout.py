"""Check discrete equivariance and byte equality of aligned continuous Pair latents separately."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from data import dataset,relayout,coordinates
from model import AddressModel
from study import ARMS,SEEDS
from fit import device


def remap(base,mapping,shape):
    """Public layout transform. Recompute demands only, independent of neural outputs."""
    c=coordinates(*shape)
    old=base['coords'];slots={tuple(pos):i for i,pos in enumerate(old)}
    g=np.arange(len(mapping))[:,None];inverse=np.argsort(mapping,axis=1)
    moved=dict(coords=c,value=base['value'][g,inverse])
    for k in ('make_ref','finish_ref'):
        ref=np.array([[slots[tuple(v)] for v in graph] for graph in base[k]])
        moved[k]=c[mapping[g,ref[g,inverse]]]
    return moved


@torch.inference_mode()
def run(m,d,shape,dev):
    _,length,ports=shape;c=torch.as_tensor(d['coords'],device=dev);parts=[]
    for i in range(0,len(d['value']),16):
        raw=m(c,*[torch.as_tensor(d[k][i:i+16],device=dev) for k in ('make_ref','finish_ref','value')],length,ports)
        torch.mps.synchronize()
        parts.append({k:raw[k].cpu().numpy() for k in ('ptr1','ptr2','pair_latent','pair_value','result_value')})
    return {k:np.concatenate([p[k] for p in parts]) for k in parts[0]}


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();dev=device()
    shape=(4,3,3);newshape=(6,2,3);base=dataset(*shape,128,92001)
    target,both=relayout(base,6,2,92102);old=np.arange(len(base['coords']))[None,:]
    cases={'cells_only':((both//3)*3+old%3,newshape),'ports_only':((old//3)*3+both%3,shape),'both':(both,newshape)}
    result={}
    for arm in ARMS:
        for seed in SEEDS:
            key=f'{arm}-{seed}';m=AddressModel(arm).to(dev).eval();m.load_state_dict(torch.load(a.root/key/'final.pt',map_location=dev,weights_only=True))
            original=run(m,base,shape,dev);result[key]={}
            for case,(mapping,target_shape) in cases.items():
                d=remap(base,mapping,target_shape)
                if case=='both':
                    for k in d:np.testing.assert_array_equal(d[k],target[k])
                new=run(m,d,target_shape,dev);g=np.arange(len(mapping))[:,None]
                discrete=np.ones(mapping.shape,bool)
                for k in ('ptr1','ptr2'):discrete &= new[k][g,mapping]==mapping[g,original[k]]
                for k in ('pair_value','result_value'):discrete &= new[k][g,mapping]==original[k]
                left=np.ascontiguousarray(original['pair_latent']);right=np.ascontiguousarray(new['pair_latent'][g,mapping])
                same=(left.view(np.uint32)==right.view(np.uint32)).all(-1)
                result[key][case]=dict(graphs=len(g),discrete_graphs=int(discrete.all(-1).sum()),latent_bit_equal_graphs=int(same.all(-1).sum()),
                                       bit_equal_slots=int(same.sum()),slots=int(same.size),latent_max_abs=float(np.abs(left-right).max()))
    (a.root/'latent-relayout.json').write_text(json.dumps(result,indent=2)+'\n')
    print({k:{a:(b['discrete_graphs'],b['latent_bit_equal_graphs']) for a,b in v.items()} for k,v in result.items()})

if __name__=='__main__':main()
