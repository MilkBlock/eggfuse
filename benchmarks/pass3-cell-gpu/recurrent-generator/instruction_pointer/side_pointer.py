"""Learn to name a higher Cell's independent side port from the sealed root snapshot."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from alternate_proofs import digest
from higher_cell import fingerprint, read
from side_boundary import address, examples, shapes


def bits(rows,width):
    # One vector per field. Padding has zero mass rather than the code for 0.
    data=np.zeros((len(rows),width,64),dtype=np.float32)
    for j,row in enumerate(rows):
        if len(row)>width: raise ValueError('field layout exceeds compiled width')
        words=np.asarray(row,dtype='<u8')
        data[j,:len(row)] = 2*np.unpackbits(words.view(np.uint8).reshape(-1,8),axis=1).astype(np.float32)-1
    return torch.from_numpy(data)


class SidePointer(nn.Module):
    def __init__(self, units, roots, sides):
        super().__init__()
        self.fields=nn.Embedding(units,roots*sides)
        self.bias=nn.Embedding(units,1)
        self.select=nn.Sequential(nn.Linear(roots*sides,24),nn.Tanh(),nn.Linear(24,1))
        nn.init.zeros_(self.fields.weight)
        nn.init.zeros_(self.bias.weight)

    def forward(self, unit, roots, sides):
        affinity=torch.einsum('brf,bnsf->bnrs',roots,sides).flatten(2)/64
        return (affinity*self.fields(unit)[:,None,:]).sum(-1)+self.select(affinity).squeeze(-1)+self.bias(unit)


def collect(folder, donor, units, rng, budget):
    labels=defaultdict(set)
    def remember(unit,root,child,external):
        if len(external)!=1: raise ValueError('pointer expects one named boundary input')
        labels[unit['unit'],root['token']].add(address(external[0]))
    examples(folder,donor,units,remember)
    roots=defaultdict(list)
    tape=read(folder/'tape.json')['requests']
    rows=[]
    for idx,unit in enumerate(units):
        applicable=[p for p in tape if p['rule']==unit['root']]
        neg=[p for p in applicable if not labels.get((unit['unit'],p['token']))]
        kept={p['token'] for p in rng.sample(neg,min(len(neg),budget))}
        for p in applicable:
            ps=labels.get((unit['unit'],p['token']),set())
            if ps or p['token'] in kept: roots[p['run']].append((idx,unit,p,ps))
    visible={}
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            frame=json.loads(line)
            for a in frame['retired']: del visible[a['token'],a['op']]
            for a,r in frame['updates']: visible[a['token'],a['op']]=r
            for idx,u,root,positive in roots[frame['run']]:
                values=[v for x in root['parents'] for v in visible[address(x)]['hashes']]
                candidates=[a for a,v in visible.items() if v['table']==u['side'][1]]
                if not positive.issubset(candidates): raise ValueError('late label')
                wrong=[a for a in candidates if a not in positive]
                subset=sorted(positive)+rng.sample(wrong,min(24,len(wrong)))
                if subset:
                    rows.append((idx,values,[visible[a]['hashes'] for a in subset],[a in positive for a in subset]))
    return rows


def fit(root, donor_path, out):
    donor=read(donor_path/'program.json')
    training=[root/r['directory'] for r in read(root/'manifest.json') if r['origin']=='eggcc' and r['split']=='train']
    if donor_path.resolve() not in [f.resolve() for f in training]: raise ValueError('unexpected Bake donor')
    catalog=shapes(donor)
    support=Counter()
    for folder in training:
        for uid,stats in examples(folder,donor,catalog).items():
            support[uid]+=stats['roots_with_available_completion']
    tables={t['name']:i for i,t in enumerate(donor['recipe']['tables'])}
    chosen={}
    for u in catalog:
        last=u['hops'][-1]
        if len(last['tables'])!=2 or any(len(h['tables'])!=1 for h in u['hops'][:-1]): continue
        if not support[u['unit']]: continue
        old=chosen.get(u['root'])
        if old and support[old['unit']]>=support[u['unit']]: continue
        chosen[u['root']]=dict(**u,side=[last['pivot'],tables[last['tables'][1-last['pivot']]]])
    units=list(chosen.values())
    rules=donor['recipe']['rules']
    root_width=max(sum(len(a['args']) for a in rules[u['root']]['query'] if 'table' in a['call']) for u in units)
    side_width=max(len([a for a in rules[u['hops'][-1]['rule']]['query'] if 'table' in a['call']][1-u['side'][0]]['args']) for u in units)
    rng=random.Random(1703)
    rows=[r for f in training for r in collect(f,donor,units,rng,512)]
    # Each example has one null choice and a variable number of actual typed addresses.
    # Mask padded addresses; any observed equivalent certificate can own the target.
    width=max(len(r[2]) for r in rows)
    roots=bits([r[1] for r in rows],root_width).to('mps')
    sides=bits([row for r in rows for row in r[2]+[[]]*(width-len(r[2]))],side_width).reshape(len(rows),width,side_width,64).to('mps')
    ids=torch.tensor([r[0] for r in rows],device='mps')
    valid=torch.tensor([[True]+[i<len(r[2]) for i in range(width)] for r in rows],device='mps')
    targets=torch.tensor([[not any(r[3])]+r[3]+[False]*(width-len(r[3])) for r in rows],device='mps')
    positive=[i for i,r in enumerate(rows) if any(r[3])]
    negative=[i for i,r in enumerate(rows) if not any(r[3])]
    torch.manual_seed(1703)
    model=SidePointer(len(units),root_width,side_width).to('mps')
    opt=torch.optim.AdamW(model.parameters(),lr=.01)
    for step in range(320):
        batch=torch.tensor(rng.choices(positive,k=16)+rng.choices(negative,k=16),device='mps')
        scores=model(ids[batch],roots[batch],sides[batch])
        scores=F.pad(scores,(1,0),value=0.)
        loss=(scores.masked_fill(~valid[batch],-1e6).logsumexp(1)-scores.masked_fill(~targets[batch],-1e6).logsumexp(1)).mean()
        opt.zero_grad();loss.backward();opt.step()
    out.mkdir(parents=True,exist_ok=True)
    torch.save(model.cpu().state_dict(),out/'side.pt')
    used={r for u in units for r in [u['root']]+[h['rule'] for h in u['hops']]}
    result=dict(units=units,root_width=root_width,side_width=side_width,weights=digest(out/'side.pt'),
                positive=len(positive),negative=len(negative),device='mps',updates=320,
                fingerprints={r:fingerprint(rules[r]) for r in used},
                training={f.name:digest(f/'tape.json') for f in training})
    (out/'head.json').write_text(json.dumps(result,indent=2)+'\n')


class LiveSide:
    def __init__(self, folder, keep_closed=False):
        self.keep_closed=keep_closed
        self.spec=read(folder/'head.json')
        if digest(folder/'side.pt')!=self.spec['weights']: raise ValueError('stale side weights')
        self.model=SidePointer(len(self.spec['units']),self.spec['root_width'],self.spec['side_width'])
        self.model.load_state_dict(torch.load(folder/'side.pt',map_location='cpu',weights_only=True))
        self.model.eval()
        self.options={}
        self.counts=Counter()
        self.run=None
        self.cache={}

    def extend(self,units,rules):
        for i,u in enumerate(self.spec['units']):
            deps=[u['root']]+[h['rule'] for h in u['hops']]
            if any(r>=len(rules) or fingerprint(rules[r])!=self.spec['fingerprints'][str(r)] for r in deps): continue
            self.options[u['root']]=(i,len(units),u['side'][1])
            units.append(dict(root=u['root'],side=u['side'],bake_id=u['unit'],
                              hops=[(h['pc'],h['rule']) for h in u['hops']]))

    def choose(self,req,history,snapshot):
        if self.run!=snapshot.run:
            self.run=snapshot.run
            self.cache.clear()
        option=self.options.get(req['rule'])
        if option is None:return
        self.counts['decisions']+=1
        idx,unit,table=option
        if table not in self.cache:
            ports=[p for p in snapshot.ports if p.table==table]
            keys=bits([p.hashes for p in ports],self.spec['side_width'])
            self.cache[table]=ports,keys
        ports,keys=self.cache[table]
        if not ports:return
        values=[v for parent in req['parents'] for v in history.visible[address(parent)]['hashes']]
        scores=self.model(torch.tensor([idx]),bits([values],self.spec['root_width']),keys[None])[0]
        self.counts['scored_addresses']+=len(ports)
        j=int(scores.argmax())
        if scores[j]<=0:return
        chosen=ports[j]
        alias,pc=chosen.address
        req['side']=dict(address=dict(token=history.inverse[alias],op=pc),version=chosen.version)
        if self.keep_closed and 'unit' in req:
            req['closed_branch']=req['unit']
        req['unit']=unit
        self.counts['named']+=1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','out'):p.add_argument(k,type=Path)
    a=p.parse_args();fit(a.root,a.donor,a.out)
