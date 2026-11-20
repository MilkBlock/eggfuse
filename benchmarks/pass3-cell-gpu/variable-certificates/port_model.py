"""Train shared typed copy/reference heads for the already-generated proof forest."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch
from torch import nn

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'whole-pass-generation'))
import policy as forest_policy
sys.path.insert(0,str(HERE.parent/'recurrent-generator'))
from capture import read,inputs

DIM=14


def schemas(image,source,p):
    program=read(source);rules=program['recipe']['rules'];spec=read(image/'device.json');tables=read(image/'ingress.json')['tables']
    table_index={t['name']:i for i,t in enumerate(tables)}
    width=spec['layout']['WIDTH']
    with np.load(image/'device.npz') as z:rom=z['rom']
    templates={};ids=[]
    for _,_,rid,pivot,addr,_,_ in p['candidates']:
        key=int(rid),int(pivot)
        if key not in templates:
            q=rules[rid]['query'];slots={};members=[];fields=[];used=set()
            order=[int(pivot)]+[i for i in range(len(q)) if i!=pivot]
            supported=0<len(q)<=2
            for position,atom_id in enumerate(order):
                op=q[atom_id];name=op['call'].get('table')
                if name is None:supported=False;break
                t=table_index[name];n=len(op['args'])
                tid,native_width,binding,mask=map(int,rom[addr+4*position:addr+4*position+4])
                if tid!=t or native_width!=n:supported=False;break
                native=list(map(int,rom[binding:binding+n]))
                if position and any(v>=0 and v not in used for v in native[:-1]):supported=False;break
                used.update(v for v in native if v>=0)
                operands=[]
                for col,(arg,sort) in enumerate(zip(op['args'],tables[t]['schema'])):
                    symbol=('slot',slots.setdefault(arg['slot'],len(slots))) if 'slot' in arg else ('literal',str(arg['literal']))
                    operands.append((symbol,sort['name']))
                    fields.append(dict(query=atom_id,member=position,col=col,table=t,sort=sort['name'],
                                       result=col+1==n,value=symbol,address=position*width+col))
                members.append((name,operands))
            if supported:
                logical=sorted(fields,key=lambda f:(f['query'],f['col']))
                signature=json.dumps([order,members],separators=(',',':'))
                shape=hashlib.sha256(signature.encode()).hexdigest()
                # Every transported component is strictly local to a single claimed root output.
                templates[key]=dict(idx=len(templates),fields=fields,logical=logical,width=len(fields),slots=len(slots),
                                    signature=shape,held=int(shape[:8],16)%4==0,free=1,arity=len(q))
            else:templates[key]=dict(idx=len(templates),width=0,slots=0,free=0,arity=len(q),signature=None,held=False)
        ids.append(templates[key]['idx'])
    return list(templates.values()),np.asarray(ids,np.int32)


def tensors(layouts):
    width=max(t['width'] for t in layouts)
    x=np.zeros((len(layouts),width,width,DIM),np.float32)
    eligible=np.zeros(x.shape[:-1],bool);target=np.zeros(x.shape[:2],np.int64)
    equal=np.zeros(x.shape[:-1],bool);address=np.zeros((len(layouts),width),np.int32)
    real=np.zeros((len(layouts),width),bool)
    for t in layouts:
        i=t['idx']
        if not t['width']:continue
        for l,g in enumerate(t['fields']):address[i,l]=g['address']
        for j,f in enumerate(t['logical']):
            real[i,j]=True
            for k,g in enumerate(t['fields']):
                eligible[i,j,k]=f['sort']==g['sort']
                equal[i,j,k]=eligible[i,j,k] and f['value']==g['value']
                if f['address']==g['address']:target[i,j]=k
                # Static roles and relative coordinates. Neither executor winners nor source physical ids are inputs.
                x[i,j,k]=[f['col']/6,g['col']/6,(f['col']-g['col'])/6,abs(f['col']-g['col'])/6,
                         float(f['member']==0),float(g['member']==0),float(f['result']),float(g['result']),
                         float(f['table']==g['table']),float(f['value'][0]=='literal'),float(g['value'][0]=='literal'),
                         t['arity']/2,t['width']/10,j/max(1,t['width']-1)]
    return {k:torch.from_numpy(v) for k,v in dict(x=x,eligible=eligible,target=target,equal=equal,address=address,real=real).items()}


class Ports(nn.Module):
    def __init__(self):
        super().__init__()
        self.hidden=nn.Linear(DIM,16);self.parent=nn.Linear(12,16,bias=False);self.read=nn.Linear(16,2)

    def forward(self,features,latent,mask):
        h=(self.hidden(features)+self.parent(latent)[:,None,None,:]).tanh()
        return self.read(h).masked_fill(~mask[:,:,:,None],-1e4)


def train(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False)
    cases=[n for n,r in read(a.corpus/'collection.json').items() if r['split']=='train']
    assert len(cases)==4
    for seed in (1703,1709):
        torch.manual_seed(seed);rng=np.random.default_rng(seed)
        checkpoint=torch.load(a.forest/f'policy-{seed}.pt',weights_only=True)
        frozen=forest_policy.Policy(checkpoint['tables'],checkpoint['rules'])
        frozen.load_state_dict(checkpoint['state']);frozen.requires_grad_(False).eval()
        net=Ports();opt=torch.optim.Adam(net.parameters(),lr=.012);ds=[];trained=set();held=set()
        for name in cases:
            image=a.corpus/name/'input';source=a.corpus/name/'program.json';p=forest_policy.packet(image,source)
            layouts,ids=schemas(image,source,p);z=tensors(layouts)
            gold=forest_policy.labels(p,a.captures/name).numpy()
            with torch.no_grad():latent=frozen.root(torch.tensor(p['root_x'])).tanh()
            pairs=[]
            for i in np.flatnonzero(gold):
                t=layouts[ids[i]]
                if not t['width']:continue
                if t['held']:held.add(t['signature']);continue
                trained.add(t['signature']);pairs.append([int(ids[i]),int(p['candidates'][i,0])])
            ds.append((z,np.asarray(pairs),latent))
        assert trained.isdisjoint(held)
        for step in range(a.updates):
            z,pairs,lat=ds[step%len(ds)];chosen=pairs[rng.integers(0,len(pairs),48)]
            ix,parent=chosen.T;mask=z['real'][ix];score=net(z['x'][ix],lat[parent],z['eligible'][ix])
            targets=z['target'][ix][mask]
            refs=nn.functional.cross_entropy(score[:,:,:,0][mask],targets)
            v=score[:,:,:,1][mask].log_softmax(-1).masked_fill(~z['equal'][ix][mask],-1e4)
            loss=refs-v.logsumexp(-1).mean()
            opt.zero_grad();loss.backward();opt.step()
        torch.save(net.state_dict(),a.out/f'ports-{seed}.pt')
        report=dict(seed=seed,train_programs=cases,supervision='published parent and source-winning child',updates=a.updates,
                    seen=sorted(trained),held=sorted(held),trained_rows=[len(d[1]) for d in ds],
                    params=sum(p.numel() for p in net.parameters()),loss=float(loss.detach()))
        (a.out/f'train-{seed}.json').write_text(json.dumps(report,indent=1)+'\n')
        print(seed,len(trained),len(held),report['loss'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','captures','forest','out'):p.add_argument(k,type=Path)
    p.add_argument('--updates',type=int,default=400)
    train(p.parse_args())
