"""Label the Actor's own named tuples by distinct teacher commit, then train second-batch utility."""
import argparse
import json
from collections import Counter
from pathlib import Path

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from anchor_set_audit import check,load_actor
from higher_cell import read
from history import History
from prefix_policy import Policy,generate
from prefix_recovery import Recovery
from ripsat_layout import signatures
from sibling_issue import Allocation,SiblingHead


@torch.no_grad()
def collect(root,name,memory,weights,recovery,binary,out,training):
    folder=root/name
    entry=next(r for r in read(root/'manifest.json') if r['directory']==name)
    if entry['origin']!='eggcc' or (entry['split']=='train')!=training:
        raise ValueError('wrong program partition')
    actor=load_actor(weights,True)
    prog=read(folder/'program.json')
    cat=actor.catalog_type(prog)
    held={i for i,s in enumerate(signatures(prog)) if int(s[:8],16)%8==0}
    nodes=actor.template_graph(cat)
    history=History(cat,1703+entry['seed'])
    probes=[]
    samples=[]
    def record(rule,order,points,features,first,base,remaining):
        if training and rule in held:
            return
        start=len(probes)
        for row in points.tolist():
            parents=[None]*len(order)
            for role,j in zip(order,row,strict=True):
                p=mem.ports[j]
                alias,op=p.address
                parents[role]=dict(address=dict(token=history.inverse[alias],op=op),version=p.version)
            probes.append(dict(token=len(probes)+1,run=snap.run,rule=rule,parents=parents))
        samples.append(dict(run=snap.run,rule=rule,held=rule in held,start=start,x=features,
                            first=first,base=base,remaining=remaining))
    head=Recovery(recovery,weights)
    policy=Policy(64,recovery=head,allocation=Allocation(32,observe=record))
    with memory.open() as frames:
        for line in frames:
            snap=history.snapshot(json.loads(line))
            mem=actor.memory(cat,snap,nodes)
            for _ in generate(actor,cat,mem,policy):
                pass
    tape=read(folder/'tape.json')
    verdict=check(folder,binary,tape,probes)
    labels=torch.zeros(len(probes),dtype=torch.long)
    for run,token,winner,_ in verdict['recall_verdicts']:
        if probes[token-1]['run']!=run:
            raise ValueError('wrong teacher snapshot')
        labels[token-1]=winner or 0
    for row in samples:
        start=row.pop('start')
        row['y']=labels[start:start+len(row['x'][0])].clone()
    out.mkdir(parents=True,exist_ok=True)
    target=out/(name+'.pt')
    torch.save(samples,target)
    info=dict(case=name,split=entry['split'],program=digest(folder/'program.json'),tape=digest(folder/'tape.json'),
              actor=digest(weights),recovery=head.checkpoint,binary=digest(binary),data=digest(target),
              requests=len(probes),groups=len(samples),runs=history.run,cap=32,frontier=64)
    (out/(name+'.json')).write_text(json.dumps(info,indent=2)+'\n')


def batch_loss(head,items,context,device):
    features=[torch.cat([s['x'][i][s['remaining']] for s in items]).to(device) for i in range(3)]
    logits=head(*features,context)
    # Each reachable new native commit carries equal positive mass within its pool.
    # Every proposal for an already covered commit and every failed proof is negative.
    labels=[]; weights=[]
    for s in items:
        y=s['y'][s['remaining']]
        positive=(y>0)&~torch.isin(y,s['y'][s['first']])
        _,inverse,counts=torch.unique(y,return_inverse=True,return_counts=True)
        weight=torch.where(positive,1/counts[inverse],1.0)
        # Balance useful and costly choices per pool, including all-negative pools.
        weight=weight/torch.where(positive,weight[positive].sum().clamp_min(1),(~positive).sum().clamp_min(1))
        labels.append(positive); weights.append(weight)
    return F.binary_cross_entropy_with_logits(logits,torch.cat(labels).to(device).float(),
            weight=torch.cat(weights).to(device),reduction='sum')/len(items)


def fit(data,out,context):
    reports={n:read(data/(n+'.json')) for n in ('sum','dot')}
    parts=[]
    for name,meta in reports.items():
        path=data/(name+'.pt')
        if meta['data']!=digest(path) or meta['split']!='train' or meta['recovery']!=reports['sum']['recovery']:
            raise ValueError('incompatible sibling training data')
        parts.extend(torch.load(path,weights_only=True))
    if not parts: raise ValueError('no contested training pools')
    torch.manual_seed(1703)
    width=parts[0]['x'][1].shape[-1]
    head=SiblingHead(width).to('mps')
    optim=torch.optim.AdamW(head.parameters(),lr=.003)
    for _ in range(40):
        for ids in torch.randperm(len(parts)).split(32):
            loss=batch_loss(head,[parts[j] for j in ids.tolist()],context,'mps')
            optim.zero_grad();loss.backward();optim.step()
    out.mkdir(parents=True,exist_ok=True)
    head.cpu().eval()
    torch.save(head.state_dict(),out/'head.pt')
    result=dict(training=reports,head=digest(out/'head.pt'),width=width,context=context,cap=32,
                recovery=reports['sum']['recovery'],device='mps',epochs=40,seed=1703)
    (out/'training.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    c=commands.add_parser('collect')
    c.add_argument('name')
    for k in ('root','memory','weights','recovery','binary','out'): c.add_argument(k,type=Path)
    c.add_argument('--training',action='store_true')
    f=commands.add_parser('fit')
    for k in ('data','out'): f.add_argument(k,type=Path)
    f.add_argument('--context',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    if a.command=='collect': collect(a.root,a.name,a.memory,a.weights,a.recovery,a.binary,a.out,a.training)
    else: fit(a.data,a.out,a.context)
