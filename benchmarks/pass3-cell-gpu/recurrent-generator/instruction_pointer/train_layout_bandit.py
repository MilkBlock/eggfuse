"""Learn a shared layout policy from logged stochastic native executions."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from alternate_proofs import digest
from higher_cell import read
from ripsat_replay import unpack
from train_ripsat import layout_id


def fixed_features(baked):
    codes=torch.load(baked/'codes.pt',map_location='cpu',weights_only=True)['codes']
    sizes=[]
    desc=[]
    for graph in unpack(read(baked/'catalog.json')):
        inputs={slot for _,_,w in graph for owner,slot in w if owner<0}
        sizes.append(len(graph))
        desc.append((len(graph),len(inputs),graph[-1][1]+1,sum(len(w) for _,_,w in graph)))
    # Including the standalone action as index zero keeps its utility explicit.
    graph=torch.cat((codes,torch.tensor(desc,dtype=torch.float32).log1p()),1)
    return F.pad(graph,(0,0,1,0)),[0]+sizes


class Utility(nn.Module):
    """No parameters are indexed by catalog or rule identity."""
    def __init__(self,width,graph_width):
        super().__init__()
        self.query=nn.Sequential(nn.Linear(width,24),nn.Tanh(),nn.Linear(24,17))
        self.key=nn.Sequential(nn.Linear(graph_width,24),nn.Tanh(),nn.Linear(24,16))
        self.bias=nn.Linear(16,1)

    def forward(self,context,graphs):
        q=self.query(context)
        k=self.key(graphs)
        scores=q[:,:-1]@k.T/4+self.bias(k).squeeze(-1)+q[:,-1:]
        return F.pad(scores[:,1:],(1,0),value=0.)


def logging_prior(options,baseline,sizes):
    freq=Counter(sizes[i] for i in options)
    p=[.15]+[.45/(len(freq)*freq[sizes[i]]) for i in options]
    p[0 if baseline==0 else options.index(baseline)+1]+=.4
    return p


class LearnedChoice:
    def __init__(self,folder,baked):
        info=read(folder/'training.json')
        for name in ('codes.pt','catalog.json','shared.pt','boundary.pt'):
            if info['bake'][name]!=digest(baked/name):
                raise ValueError('policy trained on different Bake data')
        if info['policy']!=digest(folder/'policy.pt'):
            raise ValueError('policy checkpoint changed')
        self.checkpoint=info['policy']
        self.graph,self.sizes=fixed_features(baked)
        self.model=Utility(self.graph.shape[1]-4,self.graph.shape[1])
        self.model.load_state_dict(torch.load(folder/'policy.pt',map_location='cpu',weights_only=True))
        self.model.eval()
        self.keys=self.model.key(self.graph).detach()
        self.bias=self.model.bias(self.keys).squeeze(-1).detach()

    def select(self,req,options,context,issuer):
        ready=issuer.model(context.expand(len(options),-1),issuer.codes[options])[:,1]
        j=int(ready.argmax())
        ids=[u+1 for u in options]
        baseline=ids[j] if ready[j]>0 else 0
        prior=context.new_tensor(logging_prior(ids,baseline,self.sizes))
        q=self.model.query(context)
        logits=(self.keys[ids]@q[:-1])/4+self.bias[ids]+q[-1]
        action=int((prior.log()+F.pad(logits,(1,0))).argmax())
        winner=ids[action-1] if action else 0
        if winner!=baseline:
            issuer.claim_counts['changed_layout_decisions']+=1
            if winner and not baseline:
                issuer.claim_counts['new_graph_issuance_decisions']+=1
        return winner-1 if winner else None


def dataset(paths,baked,device,sizes):
    required=read(baked/'study.json')['training']
    held={i+1 for i,g in enumerate(unpack(read(baked/'catalog.json'))) if int(layout_id(g)[:8],16)%8==0}
    menus={}
    menu_ids=[]
    contexts=[]
    chosen=[]
    baseline=[]
    propensity=[]
    rewards=[]
    positives=0
    arms=set()
    for path in paths:
        report=read(path)
        if (not report['explore'] or not report['omit'] or not report['attach'] or
            report['tape']!=required[report['program']] or report['catalog']!=digest(baked/'catalog.json')):
            raise ValueError('incompatible exploration trajectory')
        with gzip.open(path.with_suffix('.json.gz'),'rt') as stream:
            log=json.load(stream)
        catalog=[tuple(u+1 for u in opt) for opt in log['menus']]
        if any(held.intersection(opt) for opt in catalog):
            raise ValueError('training menus contain held layouts')
        local=[menus.setdefault(opt,len(menus)) for opt in catalog]
        for m,x,u,p,old,c,_ in log['rows']:
            action=0 if u is None else u+1
            prev=0 if old is None else old+1
            opts=catalog[m]
            pos=0 if not action else opts.index(action)+1
            menu_ids.append(local[m]);contexts.append(x);chosen.append(pos)
            baseline.append(0 if not prev else opts.index(prev)+1)
            propensity.append(p)
            r=c.get('uncontested_effects',0)+c.get('owned_valid',0)-c.get('failed_steps',0)/16
            positives+=r>0
            if action:arms.add(action)
            rewards.append(r)
    width=max(map(len,menus))+1
    menu=torch.zeros(len(menus),width,dtype=torch.long)
    prior=torch.zeros(len(menus),width)
    for opt,m in menus.items():
        n=len(opt)+1
        menu[m,1:n]=torch.tensor(opt)
        # Remaining 0.4 mass goes to the original greedy decision for this context.
        p=logging_prior(list(opt),0,sizes)
        p[0]-=.4
        prior[m,:n]=torch.tensor(p)
    rows=[torch.tensor(v) for v in (menu_ids,contexts,chosen,baseline,propensity,rewards)]
    return ([v.to(device) for v in rows],menu.to(device),prior.to(device),
            dict(samples=len(rewards),positive=positives,distinct_sampled_layouts=len(arms)))


def fit(logdir,baked,out):
    graph,sizes=fixed_features(baked)
    paths=sorted(logdir.glob('*.json'))
    reports=[read(p) for p in paths]
    if len({v['binary'] for v in reports})!=1:
        raise ValueError('training mixes receiver builds')
    study=read(baked/'study.json')
    for report in reports:
        if (report['actor']!=study['root_weights'] or report['scorer']!=study['weights'] or
            report['reader']!=digest(baked/'boundary.pt') or report['policy'] is not None):
            raise ValueError('logging policy differs from the frozen actor and Bake heads')
    seeds=sorted({v['seed'] for v in reports})
    if len(seeds)<4:
        raise ValueError('at least four rollout seeds required')
    names=set(read(baked/'study.json')['training'])
    if {(v['program'],v['seed']) for v in reports}!={(n,s) for n in names for s in seeds}:
        raise ValueError('incomplete crossed program/seed data')
    critics=[p for p,v in zip(paths,reports) if v['seed'] in seeds[::2]]
    policies=[p for p in paths if p not in critics]
    torch.manual_seed(1703)
    device='mps'
    graph=graph.to(device)
    critic=Utility(graph.shape[1]-4,graph.shape[1]).to(device)
    actor=Utility(graph.shape[1]-4,graph.shape[1]).to(device)
    # Start at the logging distribution, including abstention.
    nn.init.zeros_(actor.query[-1].weight);nn.init.zeros_(actor.query[-1].bias)
    nn.init.zeros_(actor.bias.weight);nn.init.zeros_(actor.bias.bias)
    summaries={}
    for phase,files,model in [('critic',critics,critic),('policy',policies,actor)]:
        (ms,x,a,b,p,r),menu,prior,summary=dataset(files,baked,device,sizes)
        opt=torch.optim.AdamW(model.parameters(),lr=.003)
        for epoch in range(3):
            order=torch.randperm(len(r))
            for ix in order.split(256):
                ii=ix.to(device)
                candidates=menu[ms[ii]]
                if phase=='critic':
                    ids=candidates.gather(1,a[ii,None]).squeeze(1)
                    # Only the logged action has an observed return.
                    q=critic.query(x[ii]);k=critic.key(graph[ids])
                    val=(q[:,:-1]*k).sum(1)/4+critic.bias(k).squeeze(-1)+q[:,-1]
                    val=val.masked_fill(ids==0,0)
                    loss=F.mse_loss(val,r[ii])
                else:
                    base=prior[ms[ii]].scatter_add(1,b[ii,None],torch.full_like(p[ii,None],.4))
                    logged=base.gather(1,a[ii,None]).squeeze(1)
                    if epoch==0 and not torch.allclose(logged,p[ii],atol=1e-6):
                        raise ValueError('logged propensity does not match available actions')
                    logbase=base.clamp_min(1e-20).log()
                    logits=actor(x[ii],graph).gather(1,candidates)+logbase
                    logpi=F.log_softmax(logits.masked_fill(base==0,-1e6),dim=1)
                    pi=logpi.exp()
                    with torch.no_grad():
                        value=critic(x[ii],graph).gather(1,candidates)
                    ratio=pi.gather(1,a[ii,None]).squeeze(1)/p[ii]
                    residual=r[ii]-value.gather(1,a[ii,None]).squeeze(1)
                    objective=(pi*value).sum(1)+ratio.clamp(max=8)*residual
                    kl=(pi*(logpi-logbase)).sum(1)
                    loss=(.03*kl-objective).mean()
                opt.zero_grad();loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(),2.)
                opt.step()
        summaries[phase]=dict(**summary,files=[p.stem for p in files])
    out.mkdir(exist_ok=True,parents=True)
    torch.save(actor.cpu().state_dict(),out/'policy.pt')
    result=dict(bake={k:digest(baked/k) for k in ('codes.pt','catalog.json','shared.pt','boundary.pt')},
                policy=digest(out/'policy.pt'),binary=reports[0]['binary'],data=summaries,device=device,
                epochs=3,importance_cap=8,kl=.03,penalty_per_failed_step=1/16,
                trajectories={p.name:digest(p.with_suffix('.json.gz')) for p in paths})
    (out/'training.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('logs','baked','out'):p.add_argument(key,type=Path)
    args=p.parse_args()
    torch.set_num_threads(1)
    fit(args.logs,args.baked,args.out)
