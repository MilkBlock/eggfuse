"""Two neural root rows, followed by two rows pointing to generated parents and typed Bake joins."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from feedback import training_reply
from model import Actor, HIDDEN, RANKS, ROWS, set_loss


def pair_joins(program):
    leaves=len(program['spine_blocks']['entries'])
    return [(leaves+i,j['left'],j['output'],j['right']) for i,j in enumerate(program['iterative_bake']['joins'])
            if j['left']<leaves and j['right']<leaves]


def compiled_actions(program, units):
    """Compile observed Bake recipes and intern their executable suffixes."""
    entries = program["spine_blocks"]["entries"]
    rules = program["recipe"]["rules"]
    recipes = [() for _ in entries]
    roots = list(range(len(entries)))
    for join in program["iterative_bake"]["joins"]:
        left, right = join["left"], join["right"]
        if not (0 <= left < len(recipes) and 0 <= right < len(recipes)):
            raise ValueError("non-topological Bake join")
        root = roots[left]
        producer = recipes[left][-1][2] if recipes[left] else root
        consumer = roots[right]
        edge = (producer, join["output"], consumer)
        recipes.append(recipes[left] + (edge,) + recipes[right])
        roots.append(root)

    joins = pair_joins(program)
    indices = {recipes[row[0]]: i for i, row in enumerate(joins)}
    tails = [-1] * len(joins)
    wires = [row[2] for row in joins]
    next_wire = max(wires, default=-1) + 1
    ids = {recipe: unit for unit, recipe in enumerate(recipes) if recipe}
    def intern(recipe, unit):
        nonlocal next_wire
        if recipe in indices and joins[indices[recipe]][0] == unit:
            return indices[recipe]
        left, port, right = recipe[0]
        producer = rules[entries[left]["consumer"]]
        consumer = rules[entries[right]["consumer"]]
        effect = producer["effects"][port]
        atom = consumer["query"][entries[right]["pivot"]]
        if effect["op"] not in ("set","let") or effect.get("call",{}).get("table") != atom["call"]["table"]:
            raise ValueError(f"unit {unit}: incompatible effect and pivot")
        rest = recipe[1:]
        tail = -1
        if rest:
            if rest not in indices:
                suffix_id = ids.get(rest, len(recipes) + len(joins))
                intern(rest, suffix_id)
            tail = indices[rest]
        index = len(joins)
        joins.append((unit, left, port, right))
        tails.append(tail)
        wires.append(next_wire)
        next_wire += 1
        indices[recipe] = index
        return index

    for unit in units:
        if not len(entries) <= unit < len(recipes):
            raise ValueError(f"invalid Bake unit {unit}")
        intern(recipes[unit], unit)
    return joins, tails, wires


class CompoundActor(nn.Module):
    def __init__(self,joins,wires=None):
        super().__init__()
        self.root=Actor()
        self.register_buffer('joins',torch.tensor(joins),persistent=False)
        self.register_buffer('wires',torch.tensor(wires if wires is not None else [j[2] for j in joins]),persistent=False)
        self.score=nn.Parameter(torch.randn(len(joins),14)*.04)
        self.row_score=nn.Parameter(torch.zeros(ROWS,len(joins)))
        self.embedding=nn.Parameter(torch.randn(len(joins),HIDDEN)*.08)
        self.null=nn.Parameter(torch.zeros(ROWS))
        self.row_latent=nn.Parameter(torch.randn(ROWS,HIDDEN)*.05)

    def propose_children(self,parents,verdict,visible,run,choose=None):
        batch=len(parents);device=parents.device
        lanes=torch.arange(ROWS,device=device)
        hidden=parents[...,:HIDDEN]
        receipt=verdict[...,0]
        context=torch.cat([hidden,torch.ones_like(hidden[...,:1]),(visible & (receipt==1)).float()[...,None],
                           (visible & (receipt==2)).float()[...,None],(visible & (receipt==3)).float()[...,None],
                           parents[...,HIDDEN+2:HIDDEN+3]/RANKS],-1)
        scores=context@self.score[:,:13].T
        scores=scores[:,None,:,:]+self.row_score[None,:,None,:]+torch.eye(ROWS,device=device)[None,:,:,None]*self.score[:,13]
        legal=(parents[:,:,HIDDEN,None].long()==self.joins[:,1]+1)
        scores=scores.masked_fill(~legal[:,None],-1e4).reshape(batch,ROWS,-1)
        logits=torch.cat([self.null[None,:,None].expand(batch,-1,-1),scores],-1)
        action=logits.argmax(-1) if choose is None else choose(logits)
        idx=(action-1).clamp_min(0);parent=idx//len(self.joins);join=idx%len(self.joins)
        active=action!=0
        parent=torch.where(active,parent,lanes)
        latent=hidden.gather(1,parent[:,:,None].expand(-1,-1,HIDDEN))
        latent=(latent+self.row_latent+active[:,:,None]*self.embedding[join]).tanh()
        address=(run[:,None]-1)*ROWS+parent+1
        fields=torch.stack([self.joins[join,3]+1,address,self.wires[join]+1,active],-1)*active[:,:,None]
        return logits,torch.cat([latent,fields.float()],-1),action


def train(a,seed):
    torch.manual_seed(seed);torch.set_num_threads(1)
    rng=np.random.default_rng(seed)
    units=a.three_step
    if units is None:
        observed=set()
        for target in (a.targets/'train').glob('*.npz'):
            with np.load(target) as z:
                observed.update(int(row[3]) for row in z['targets'] if row[4]>2)
        units=sorted(observed)
    joins,tails,wires=compiled_actions(json.loads(a.donor.read_bytes()),units)
    actor=CompoundActor(joins,wires)
    donor_ids={j[0]:i for i,j in enumerate(joins)}
    datasets=[]
    names=sorted(p.stem for p in (a.targets/'train').glob('*.npz'))
    assert len(names)==4
    for n in names:
        with np.load(a.data/n/'training.npz') as z:
            features=torch.from_numpy(z['features']);positive=torch.from_numpy(z['positive']);receipt=torch.from_numpy(z['receipt'])
        paths=torch.zeros(len(positive),positive.shape[1],len(joins),dtype=torch.bool)
        with np.load(a.targets/'train'/f'{n}.npz') as z:
            for run,leaf,rank,unit,depth,*_ in z['targets']:
                if depth>=2 and unit in donor_ids:paths[run-1,leaf*RANKS+rank,donor_ids[unit]]=True
        shapes=[]
        for index in range(len(joins)):
            shape=[]
            while index>=0:
                shape.append(joins[index][1:])
                index=tails[index]
            shapes.append(shape)
        for action in sorted(range(len(joins)),key=lambda i:len(shapes[i]),reverse=True):
            for prefix,shape in enumerate(shapes):
                if len(shape)<len(shapes[action]) and shapes[action][:len(shape)]==shape:
                    paths[:,:,prefix] &= ~paths[:,:,action]
        datasets.append((features,positive,receipt,paths,np.flatnonzero(paths.any((1,2)).numpy())))
    opt=torch.optim.Adam(actor.parameters(),lr=.006)
    losses=[]
    for update in range(a.updates):
        samples=[]
        for j in range(12):
            x,y,r,g,h=datasets[int(rng.integers(len(names)))]
            end=int(rng.choice(h) if j%3 else rng.integers(7,len(x)))
            start=max(0,end-7)
            samples.append((x[start:start+8],y[start:start+8],r[start:start+8],g[start:start+8],torch.arange(start+1,start+9)))
        x,y,r,g,source_run=map(torch.stack,zip(*samples))
        prev=torch.zeros(len(x),ROWS,HIDDEN+4);loss=0
        for t in range(x.shape[1]):
            logits,roots=actor.root.step(x[:,t],prev)
            productive=g[:,t].any(-1)
            root_target=torch.where(productive.any(-1)[:,None],productive,y[:,t]) if a.root_target=="continuation" else y[:,t]
            loss=loss+set_loss(logits,root_target)
            verdict,_=training_reply(roots.detach(),r[:,t],torch.zeros_like(y[:,t]))
            visible=torch.rand(len(x),1)>.5
            child_logits,prev,_=actor.propose_children(roots,verdict,visible,source_run[:,t])
            action=((roots[...,HIDDEN].long()-1)*RANKS+roots[...,HIDDEN+2].long()-1).clamp_min(0)
            labels=g[:,t].gather(1,action[...,None].expand(-1,-1,len(joins))) & (verdict[...,0:1]==1)
            loss=loss+set_loss(child_logits,labels.reshape(len(x),-1))
        loss=loss/(2*x.shape[1]);opt.zero_grad();loss.backward()
        nn.utils.clip_grad_norm_(actor.parameters(),1.);opt.step()
        if update%40==0:losses.append(float(loss.detach()))
    out=a.out/f'train-{seed}';out.mkdir(parents=True,exist_ok=False)
    torch.save(actor.state_dict(),out/'actor.pt')
    native=torch.cat([p.detach().flatten() for p in (actor.score,actor.row_score,actor.embedding,actor.null,actor.row_latent)]).tolist()
    (out/'policy.json').write_text(json.dumps(dict(schema='eggfuse.compound-chain/v1' if units else 'eggfuse.compound-pair/v1',joins=joins,three_step=units,tails=tails,wires=wires,
        named_boundary=True,roots=actor.root.metal_weights(),child=native,seed=seed,root_target=a.root_target,train=names,updates=a.updates,loss=losses),separators=(',',':'))+'\n')
    print(seed,len(joins),losses,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('donor','data','targets','out'):p.add_argument(k,type=Path)
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--three-step',type=int,nargs='*',default=None)
    p.add_argument('--updates',type=int,default=480)
    p.add_argument('--root-target',choices=('leaf','continuation'),default='continuation')
    a=p.parse_args()
    for seed in a.seeds:train(a,seed)
