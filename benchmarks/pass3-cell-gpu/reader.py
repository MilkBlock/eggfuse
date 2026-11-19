"""Device-only incidence probe. Reads the packet, never the source graph or CPU trace."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from run import pointer
from ports import load


@torch.inference_mode()
def read(path,weights,ports,out,join):
    if not torch.backends.mps.is_available():raise RuntimeError('MPS required')
    spec=json.loads(path.read_text());layout=spec['layout'];dev=torch.device('mps')
    with np.load(path.with_name('device.npz')) as f:
        rom=torch.as_tensor(f['rom'],device=dev).long()
        members=torch.as_tensor(f['members'],device=dev).long()
        sort=torch.as_tensor(f['eq_sort'],device=dev)
    physical,selected=pointer(weights,layout['NINST'],dev)
    slots=torch.arange(layout['NINST'],device=dev)
    # The model actually selects a descriptor out of the shuffled bank.
    bank=rom[layout['INSTANCE']:layout['INSTANCE']+3*len(slots)].reshape(-1,3)[physical]
    desc=bank[selected][members[:,0]];tid=desc[:,0]
    base=rom[layout['TEMPLATE']+2*tid+1];member=base+3*members[:,1]
    tab=rom[member];width=rom[member+1]
    hidden=(desc[:,2]>>members[:,1])&1
    model=load(ports,dev);candidates=torch.arange(-1,layout['WIDTH'],device=dev)
    # Query every ordered input position and the result; include absent ports.
    q=torch.arange(-1,layout['WIDTH'],device=dev).expand(len(tab),-1)
    w=width[:,None].expand_as(q)
    got=candidates[model(w.flatten(),q.flatten(),candidates).argmax(-1)].reshape_as(q)
    op_index=rom[rom[member+2][:,None]+got.clamp_min(0)]
    upstream=base[:,None]+3*(-1-op_index).clamp_min(0)
    upstream=upstream.clamp_max(len(rom)-3)
    resolved=torch.where(op_index<0,rom[(rom[upstream+2]+rom[upstream+1]-1).clamp(0,len(rom)-1)],op_index)
    symbols=rom[desc[:,1,None]+resolved]
    symbols=torch.where(got>=0,symbols,-1)
    # Stable instance/member addresses survive an Eq merge. Class queries go
    # through this separate parent map. These are controlled, same-sort input
    # events; the caller supplies the two class handles as in an actual union.
    parent=torch.arange(layout['NSYMBOLS'],device=dev)
    accepted=torch.tensor(False,device=dev)
    if join is not None:
        a,b=join
        if not (0<=a<len(parent) and 0<=b<len(parent)):raise ValueError('outside class dictionary')
        accepted=(sort[a]>=0)&(sort[a]==sort[b])
        parent[max(a,b)]=torch.where(accepted,min(a,b),max(a,b))
    current=torch.where(symbols>=0,parent[symbols.clamp_min(0)],-1)
    def host(v):return v.cpu().numpy()
    np.savez_compressed(out,selected=host(physical[selected]),refs=host(members),table=host(tab),
                        union_accepted=host(accepted),hidden=host(hidden),role=host(got),raw=host(symbols),current=host(current))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('image','address_weights','port_weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--union',type=int,nargs=2)
    a=p.parse_args();read(a.image,a.address_weights,a.port_weights,a.out,a.union)
