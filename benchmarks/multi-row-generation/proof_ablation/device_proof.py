from functools import lru_cache
from pathlib import Path
import hashlib

import torch

from bake import bake


@lru_cache(maxsize=1)
def library():
    return torch.mps.compile_shader(Path(__file__).with_name('proof.metal').read_text())


def compiled(template,plan,dev):
    bank=bake(plan)
    def tensor(x):return torch.tensor(x,dtype=torch.int32,device=dev)
    physical=[-1]*(max(plan['ports'])+1)
    for i,p in enumerate(plan['ports']):physical[p]=i
    # Process-local compact template version tag; reject collisions in the installed catalog.
    tag=int.from_bytes(hashlib.sha256(template['version'].encode()).digest()[:4],'little') & 0x7fffffff
    peak=max(m[-1] for m in bank['macros'])
    rules=[0]*len(plan['implications'])
    for i,r in enumerate(plan['implications']):
        rules[i]=len(rules);rules.extend((*r['unifies'],len(r['requires'])))
        for pair in r['requires']:rules.extend(pair)
    cfg=[tag,2,plan['vertices'],len(bank['macros']),peak,len(plan['implications']),*bank['public'],*plan['local_pair']]
    return dict(cfg=tensor(cfg),routes=tensor(bank['routes']),macro=tensor(bank['macros']),code=tensor(bank['code']),
                rules=tensor(rules or [0]),ports=tensor(physical),peak=peak)


def records(x,stages,token,plan):
    a,b,req,ap,rp,phase,commit,ext,ep=x
    lookup=plan['ports']
    def pack(s):return torch.cat((s['active'][...,None],s['pointers'],s['rows']),-1).int().contiguous()
    a_addr=3*a[...,0]+lookup[ap.long()]
    inputs=torch.cat((a,a_addr[...,None]),-1).int().contiguous()
    _,second=stages
    parents=torch.cat((token[...,32:34].argmax(-1,keepdim=True),token[...,34:42].argmax(-1,keepdim=True),
                       token[...,42:50].argmax(-1,keepdim=True),token[...,50:55].int(),
                       (3*token[...,50].int()+lookup[token[...,-1].long()])[...,None]),-1)
    endpoints=3*req[...,[0,2]]+lookup[rp.long()]
    asks=torch.cat((req,endpoints),-1).int().contiguous()
    left=torch.where(ext[:,1]==0,ep[:,0],ep[:,1]);right=torch.where(ext[:,1]==0,ep[:,1],ep[:,0])
    edge=torch.where(ext[:,0].bool(),1+3*lookup[left.long()]+lookup[right.long()],0)
    on=((phase>=1)&commit.bool()).int()
    ctx=torch.stack((on[:,0]+2*on[:,1],edge),-1).int().contiguous()
    return (inputs,b.int().contiguous(),parents.int().contiguous(),pack(second),asks,ctx)


def issue(data,p,macro):
    _,_,_,proposal,req,ctx=data
    batch=len(req)
    wire=torch.empty((batch,8*(6+(1 if macro else p['peak']))),dtype=torch.int32,device=req.device)
    slices=torch.empty((batch,8,2),dtype=torch.int32,device=req.device)
    library().issue(proposal,req,ctx,p['routes'],p['macro'],p['code'],p['cfg'],wire,slices,int(macro),
                    threads=batch,arg_casts={9:'int32'})
    return wire,slices


def verify(data,p,wire,slices,macro):
    out=torch.empty_like(slices)
    library().verify(*data,p['cfg'],p['rules'],p['macro'],wire,slices,out,int(macro),
                     threads=len(slices)*8,arg_casts={12:'int32'})
    return out


def publish(data,verified):
    out=torch.full((len(verified),4,7),-1,dtype=torch.int32,device=verified.device)
    library().publish(data[3],verified,out,threads=len(out))
    return out
