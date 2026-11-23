"""Train the shared pointer for the independent input slots of any baked instruction graph."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random

import torch
from torch import nn
from torch.nn import functional as F

from actor import row_features
from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from ripsat_layout import capture, queries
from ripsat_policy import CellScorer, GraphBank, root_context
from ripsat_replay import unpack
from train_ripsat import layout_id


def slots(layout,rules):
    """All uses of an independent slot have the same fact type."""
    positions={}
    for j,(rid,_,wires) in enumerate(layout):
        for role,(pred,slot) in enumerate(wires):
            if pred>=0:
                continue
            table=queries(rules[rid])[role]['call']['table']
            if slot in positions and positions[slot][0]!=table:
                raise ValueError('shared boundary port has inconsistent types')
            positions.setdefault(slot,(table,[]))[1].append((j,rid,role))
    if set(positions)!=set(range(len(positions))):
        raise ValueError('independent port layout has gaps')
    return [positions[i] for i in range(len(positions))]


class BoundaryReader(nn.Module):
    def __init__(self,width):
        super().__init__()
        self.query=nn.Sequential(nn.Linear(width*3,width),nn.Tanh())
        self.key=nn.Linear(width,width)
        self.compare=nn.Sequential(nn.Linear(width+4,width),nn.Tanh(),nn.Linear(width,1))

    def forward(self,context,keys,comparison):
        q=self.query(context)
        return (q[:,None]*self.key(keys)).sum(-1)/q.shape[-1]**.5 + self.compare(
            torch.cat((q[:,None].expand(-1,keys.shape[1],-1),comparison),dim=-1)).squeeze(-1)


def fields(prior,domain,width):
    # All ports of the requested static type are scored in deployment. The
    # similarity arithmetic belongs to the reader and supplies no exact join mask.
    from side_pointer import bits
    previous=[x for row in prior for x in row]
    field_width=max(map(len,domain),default=0)
    keys=row_features(domain,width,'cpu')
    if not previous or not field_width:
        return keys,torch.zeros(len(domain),4)
    x=bits([previous],len(previous))[0]
    y=bits(domain,field_width)
    pair=torch.einsum('pf,nsf->nps',x,y)/64
    present=torch.arange(field_width)[None,:]<torch.tensor(list(map(len,domain)))[:,None]
    valid=present[:,None,:].expand_as(pair)
    best=pair.masked_fill(~valid,-1).amax((1,2))
    mean=(pair*valid).sum((1,2))/valid.sum((1,2)).clamp_min(1)
    each=pair.amax(1)
    return keys,torch.stack((best,mean,each[:,0],(each*present).sum(1)/present.sum(1).clamp_min(1)),dim=1)


def make_steps(folder,donor,layouts,selected,seed,codes,roles,model=None,*,grow_consumers=False):
    rng=random.Random(seed)
    refs,_,roots,_=capture(folder,donor,max(map(len,layouts)),grow_consumers=grow_consumers)
    ids={layouts[i]:i for i in selected}
    # Each layout contributes at most one complete certificate per program.
    by_run=defaultdict(list)
    seen=set()
    for j,items in roots.items():
        for layout,occ in items.items():
            uid=ids.get(layout)
            if uid is None or uid in seen:
                continue
            for boundary,ready,first,_ in occ:
                if ready and first:
                    by_run[refs[j]['run']].append((uid,boundary))
                    seen.add(uid)
                    break
    table={t['name']:i for i,t in enumerate(read(folder/'program.json')['recipe']['tables'])}
    visible={}
    samples=[]
    counts=Counter()
    by_size=defaultdict(Counter)
    width=codes.shape[1]
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            frame=json.loads(line)
            for a in frame['retired']:
                del visible[a['token'],a['op']]
            for a,row in frame['updates']:
                visible[a['token'],a['op']]=row
            if frame['run'] not in by_run:
                continue
            domains=defaultdict(list)
            for (t,pc),row in visible.items():
                domains[row['table']].append((t,pc,row['version']))
            for uid,boundary in by_run[frame['run']]:
                steps=layouts[uid]
                known={b for _,b in steps[0][2]}
                extra=set(range(len(boundary)))-known
                counts['ready_layouts']+=1
                if not extra:
                    counts['all_slots_from_root']+=1
                    continue
                counts['needs_pointer']+=1
                correct=True
                bound={s:boundary[s] for s in known}
                for slot in sorted(extra):
                    gold=boundary[slot]
                    tab,role=roles[uid][slot]
                    domain=domains[table[tab]]
                    if gold not in domain:
                        raise ValueError('gold boundary absent at root')
                    if model is None:
                        negatives=[p for p in domain if p!=gold]
                        domain=[gold]+rng.sample(negatives,min(15,len(negatives)))
                    hashes=[tuple(visible[p[:2]]['hashes']) for p in domain]
                    prior=[tuple(visible[bound[s][:2]]['hashes']) for s in sorted(bound)]
                    keys,features=fields(prior,hashes,width)
                    ctx=torch.cat((codes[uid],role,root_context(prior,width)))
                    if model is None:
                        samples.append((ctx,keys,features))
                        bound[slot]=gold
                    else:
                        score=model(ctx[None],keys[None],features[None])[0]
                        bound[slot]=domain[int(score.argmax())]
                        hit=bound[slot]==gold
                        counts['slots']+=1
                        counts['literal_hits']+=hit
                        counts['scored_ports']+=len(domain)
                        correct &= hit
                if model is not None:
                    counts['literal_complete']+=correct
                    by_size[len(steps)]['queries']+=1
                    by_size[len(steps)]['literal_complete']+=correct
    return samples,dict(counts=counts,by_size=by_size)


def fit(root,donor_folder,baked,root_weights,out,names):
    study=read(baked/'study.json')
    for path,key in [(root_weights,'root_weights'),(baked/'shared.pt','weights'),(baked/'catalog.json','catalog_sha')]:
        if digest(path)!=study[key]:
            raise ValueError('incompatible shared template policy')
    donor=read(donor_folder/'program.json')
    layouts=unpack(read(baked/'catalog.json'))
    actor=load_actor(root_weights,True)
    cat=actor.catalog_type(donor)
    with torch.no_grad():
        nodes=actor.template_graph(cat)
        scorer=CellScorer(actor.width)
        scorer.load_state_dict(torch.load(baked/'shared.pt',weights_only=True))
        codes=GraphBank(layouts,cat,nodes).encode(scorer)
        roles=[[(table,torch.stack([nodes[cat.inputs['generated',rid][role]] for _,rid,role in uses]).mean(0))
                for table,uses in slots(l,donor['recipe']['rules'])] for l in layouts]
    held={i for i,l in enumerate(layouts) if int(layout_id(l)[:8],16)%8==0}
    train=set(range(len(layouts)))-held
    data=[]
    train_stats={}
    if set(study['training']) & set(names):
        raise ValueError('evaluation and training programs overlap')
    for name,sha in study['training'].items():
        if digest(root/name/'tape.json')!=sha:
            raise ValueError('training tape changed')
        rows,train_stats[name]=make_steps(root/name,donor,layouts,train,1703,codes,roles,grow_consumers=study.get("grow_consumers",False))
        data.extend(rows)
    size=max(len(k) for _,k,_ in data)
    ctx=torch.stack([c for c,_,_ in data]).to('mps')
    def stack(i):
        return torch.stack([F.pad(r[i],(0,0,0,size-len(r[i]))) for r in data]).to('mps')
    keys,features=stack(1),stack(2)
    mask=(torch.arange(size)[None,:]>=torch.tensor([len(k) for _,k,_ in data])[:,None]).to('mps')
    torch.manual_seed(1703)
    model=BoundaryReader(actor.width).to('mps')
    opt=torch.optim.AdamW(model.parameters(),lr=.003)
    rng=random.Random(1703)
    order=list(range(len(data)))
    for _ in range(4):
        rng.shuffle(order)
        for start in range(0,len(order),64):
            ix=order[start:start+64]
            scores=model(ctx[ix],keys[ix],features[ix]).masked_fill(mask[ix],-1e6)
            loss=F.cross_entropy(scores,torch.zeros(len(ix),device='mps',dtype=torch.long))
            opt.zero_grad()
            loss.backward()
            opt.step()
    out.mkdir(parents=True,exist_ok=True)
    model=model.cpu().eval()
    torch.save(model.state_dict(),out/'boundary.pt')
    result=dict(training=train_stats,training_slots=len(data),weights=digest(out/'boundary.pt'),
                catalog=study['catalog_sha'],scorer=study['weights'],programs={})
    with torch.no_grad():
        for name in names:
            result['programs'][name]={}
            for group,active in [('known',train),('held',held)]:
                _,report=make_steps(root/name,donor,layouts,active,1703,codes,roles,model,grow_consumers=study.get("grow_consumers",False))
                result['programs'][name][group]=report
    (out/'boundary.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','baked','root_weights','out'):
        parser.add_argument(k,type=Path)
    parser.add_argument('--cases',nargs='+',required=True)
    a=parser.parse_args()
    torch.set_num_threads(1)
    fit(a.root,a.donor,a.baked,a.root_weights,a.out,a.cases)
