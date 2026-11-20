"""Paired complete-key pointer training. Source cases and Pass 3 answers are never loaded."""
import argparse,json
from pathlib import Path
import torch
import torch.nn.functional as F

def train(folder,signal,dim,seed):
    torch.set_num_threads(1)
    books=2 if signal in ('double_hash','source_role') else 1
    params=torch.Generator().manual_seed(seed)
    # The first eight columns agree at initialization across the four arms.
    first=torch.randn(128,8,generator=params)
    rest=torch.randn(128,8,generator=params)
    raw=first if books==1 and dim==8 else torch.cat([first,rest],1 if books==1 else 0)
    embedding=torch.nn.Parameter(raw)
    null=torch.nn.Parameter(torch.tensor(.5))
    opt=torch.optim.Adam([embedding,null],lr=.01)
    batches=torch.Generator().manual_seed(seed)
    codes=torch.Generator().manual_seed(seed+13)
    secondary=torch.randint(128,(4096,),generator=codes)
    roles=torch.randint(16,(4096,),generator=codes)
    roles[::2]=0
    channel=secondary if signal=='double_hash' else roles
    for update in range(800):
        width=1+update%4
        candidates=torch.randint(4096,(64,16,width),generator=batches)
        queries=candidates[:,0].clone()
        candidates[:,1:5,:-1]=queries[:,None,:-1]
        queries[32:]=torch.randint(4096,(32,width),generator=batches)
        truth=(candidates==queries[:,None]).all(-1)
        labels=torch.where(truth.any(-1),truth.long().argmax(-1),16)
        e=F.normalize(embedding,dim=-1)
        score=(e[queries%128][:,None]*e[candidates%128]).sum(-1).mean(-1)
        if books==2:
            other=(e[128+channel[queries]][:,None]*e[128+channel[candidates]]).sum(-1).mean(-1)
            score=(score+other)/2
        loss=F.cross_entropy(16*torch.cat([score,null.expand(64,1)],1),labels)
        opt.zero_grad();loss.backward();opt.step()
    out=folder/f'{signal}-{dim}-{seed}.json'
    out.write_text(json.dumps(dict(schema='port-pointer/v2',signal=signal,seed=seed,dim=dim,buckets=128,
        embedding=F.normalize(embedding.detach(),dim=-1).tolist(),null=null.item()),separators=(',',':'))+'\n')
    return out

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('folder',type=Path);p=a.parse_args()
    p.folder.mkdir(parents=True,exist_ok=True)
    for seed in (1703,1709):
        for mode,dim in [('single',8),('single',16),('double_hash',8),('source_role',8)]:
            train(p.folder,mode,dim,seed)
