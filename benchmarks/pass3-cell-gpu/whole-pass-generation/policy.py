"""Generate an entire two-level proof forest from a compiled source program before Pass 3."""
import argparse
import hashlib
from collections import Counter
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn


def read(path):
    return json.loads(path.read_bytes())


def packet(image,program):
    """Only source static structure and the actual initial graph are inspected here."""
    source=read(program);ingress=read(image/'ingress.json');device=read(image/'device.json')
    assert hashlib.sha256(program.read_bytes()).hexdigest()==ingress['program_sha256']
    rules=source['recipe']['rules'];tables={t['name']:i for i,t in enumerate(ingress['tables'])}
    counts=Counter(t['table'] for t in source['initial'])
    roots=[r for r,rule in enumerate(rules) if not rule['query']]
    root_x=[]
    for r in roots:
        rule=rules[r]
        root_x.append([len(rule['effects'])/1000,len(rule['slots'])/1000,len(source['initial'])/1000,
                       len(counts)/100,r/1000,1.])
    with np.load(image/'device.npz') as z:rom=z['rom']
    entries=[]
    for rid,rule in enumerate(rules):
        off=device['layout']['SPINE']+4*rid
        n,start=map(int,rom[off:off+2])
        for pivot,addr in rom[start:start+2*n].reshape(-1,2):
            entries.append((rid,int(pivot),int(addr),int(rom[addr])))
    # A single table atom with a distinct fresh variable in every column has a universal
    # projection proof. Read the lowered program to derive the exact RHS input permutation.
    projections=[-1]*len(rules);columns=[]
    for rid,pivot,addr,table in entries:
        rule=rom[device['layout']['RULE']+7*rid:][:7]
        t,width,bindings,mask=map(int,rom[addr:addr+4])
        if rule[0]!=1 or pivot!=0 or mask!=(1<<width)-1:continue
        variables=list(map(int,rom[bindings:bindings+width]))
        inputs=list(map(int,rom[rule[5]:rule[5]+rule[4]]))
        if min(variables,default=0)<0 or len(set(variables))!=width or not all(v in variables for v in inputs):continue
        projections[rid]=len(columns);columns.extend(variables.index(v) for v in inputs)
    candidates=[];child_x=[];base=0;publication=[]
    for i,r in enumerate(roots):
        rule=rules[r]
        for e,op in enumerate(rule['effects']):
            name=op.get('call',{}).get('table') if op['op']=='let' else op.get('table') if op['op']=='set' else None
            if not name or name not in tables:continue
            table=tables[name]
            for rid,pivot,addr,t in entries:
                if t!=table:continue
                candidates.append((i,e,rid,pivot,addr,t,base+e))
                child_x.append([r/1000,rid/1000,table/400,pivot/16,e/max(1,len(rule['effects'])),
                                np.log1p(counts[name])/6,len(op.get('args',[]))/8,
                                len(rules[rid]['query'])/16,len(rules[rid]['effects'])/16,
                                len(rules[rid]['slots'])/32,float(op['op']=='set'),1.])
        publication.append(base);base+=len(rule['effects'])
    # Sort by consumer for the verifier. IDs are stable for the duration of inference.
    order=sorted(range(len(candidates)),key=lambda i:(candidates[i][2],i))
    return dict(image_sha256=hashlib.sha256((image/'device.npz').read_bytes()).hexdigest(),roots=roots,root_x=np.array(root_x,np.float32),candidates=np.array([candidates[i] for i in order],np.int32),
                child_x=np.array([child_x[i] for i in order],np.float32),publication=publication,ports=base,projections=projections,columns=columns,
                table_count=len(tables),rules=len(rules),initial_rows=len(source['initial']))


def save_packet(p,path):
    np.savez_compressed(path,**p)


def load_packet(path,image):
    with np.load(path,allow_pickle=False) as z:
        p={k:(z[k].item() if z[k].ndim==0 else z[k]) for k in z.files}
    if hashlib.sha256((image/'device.npz').read_bytes()).hexdigest()!=p['image_sha256']:
        raise ValueError('source packet and static forest catalog do not match')
    return p


class Policy(nn.Module):
    """Each emitted child binds a typed port of a generated root. No binding truth enters forward."""
    def __init__(self,table_count,rules):
        super().__init__()
        self.root=nn.Linear(6,12)
        self.table=nn.Embedding(table_count,8)
        self.consumer=nn.Embedding(rules,8)
        self.child=nn.Sequential(nn.Linear(40,32),nn.Tanh(),nn.Linear(32,1))

    def forward(self,root_x,child_x,candidates):
        root_latent=self.root(root_x).tanh()
        parent=candidates[:,0].long()
        child_score=self.child(torch.cat([root_latent[parent],child_x,self.table(candidates[:,5].long()),
                                          self.consumer(candidates[:,2].long())],1))[:,0]
        return root_latent,child_score



def labels(p,source):
    with np.load(source/'neural-inputs.npz') as z,np.load(source/'output.npz') as g:
        rhs=g['rhs'];pivot=z['pivot'];consumed=z['consumed'];publications=z['publications']
        known=set()
        for child in np.flatnonzero(consumed):
            parent,effect,_,_=publications[consumed[child]-1]
            known.add((int(rhs[parent-1,1]),int(effect),int(rhs[child,1]),int(pivot[child])-1))
    return torch.tensor([(p['roots'][i],e,r,j) in known for i,e,r,j,*_ in p['candidates']],dtype=torch.float32)


def train(a):
    datasets=[]
    for name,obj in read(a.corpus/'collection.json').items():
        if obj['split']!='train':continue
        p=packet(a.corpus/name/'input',a.corpus/name/'program.json')
        datasets.append((name,p,labels(p,a.captures/name)))
    assert len(datasets)==4
    a.out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1)
    for seed in [1703,1709]:
        torch.manual_seed(seed)
        n_tables=max(d['table_count'] for _,d,_ in datasets);n_rules=max(1024,max(d['rules'] for _,d,_ in datasets))
        net=Policy(n_tables,n_rules);optimizer=torch.optim.Adam(net.parameters(),lr=.01)
        for step in range(400):
            name,d,y=datasets[step%4];idx=torch.from_numpy(d['candidates'])
            _,score=net(torch.from_numpy(d['root_x']),torch.from_numpy(d['child_x']),idx)
            # Keep a fixed positive class weight across families. Held-out labels never set the threshold.
            loss=nn.functional.binary_cross_entropy_with_logits(score,y,pos_weight=torch.tensor(2.))
            optimizer.zero_grad();loss.backward();optimizer.step()
        torch.save(dict(state=net.state_dict(),tables=n_tables,rules=n_rules,seed=seed,
                        train=[n for n,_,_ in datasets]),a.out/f'policy-{seed}.pt')
        print(seed,[(n,len(y),int(y.sum())) for n,_,y in datasets],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','captures','out'):ap.add_argument(name,type=Path)
    train(ap.parse_args())
