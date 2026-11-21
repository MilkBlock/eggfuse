"""Supervise individual births, or optimize expected true staged births under the real per-rule quotas."""
import argparse,json
from pathlib import Path
import torch
from torch import nn

DONORS=('sum-bits','dot-product','jacobi-1d')

def frequency_table(data):
    totals={}
    for case in data:
        for features,(no,yes) in case['hist']:
            pair=totals.setdefault(tuple(features),[0,0]);pair[0]+=no;pair[1]+=yes
    return totals

def contested(data,ids):
    # Each row is a multiplicity of identical observable features within one concrete selection.
    indices=[];sizes=[];wins=[];owners=[];quotas=[]
    for case in data:
        for _,_,grant,rows in case['groups']:
            total=sum(n+y for _,n,y in rows)
            if not 0<grant<total:continue
            owner=len(quotas);quotas.append(grant)
            for x,n,y in rows:
                owners.append(owner);indices.append(ids[tuple(x)]);sizes.append(n+y);wins.append(y)
    return (torch.tensor(indices),torch.tensor(owners),*[torch.tensor(l,dtype=torch.float64) for l in (sizes,wins,quotas)])

def marginal_derivative(z,owner,n,y,k):
    # A shared threshold per group gives inclusion probabilities whose sum is
    # exactly its grant (up to bisection tolerance). Any such vector is a
    # mixture of K-hot actions. Additive physical return only needs marginals.
    with torch.no_grad():
        lo=torch.full_like(k,float(z.min())-36);hi=torch.full_like(k,float(z.max())+36)
        for _ in range(30):
            mid=(lo+hi)*.5
            p=torch.sigmoid(z-mid[owner])
            used=torch.zeros_like(k).index_add_(0,owner,n*p)
            lo=torch.where(used>k,mid,lo);hi=torch.where(used>k,hi,mid)
        p=torch.sigmoid(z-((lo+hi)*.5)[owner])
        slope=p*(1-p)
        mass=torch.zeros_like(k).index_add_(0,owner,n*slope)
        reward=torch.zeros_like(k).index_add_(0,owner,y*slope)
        return slope*(y-n*(reward/mass.clamp_min(1e-20))[owner])/k.sum()

def export(model,hidden):
    if hidden:
        return dict(hidden=model[0].weight.detach().tolist(),hidden_bias=model[0].bias.detach().tolist(),
                    output=model[-1].weight.detach().flatten().tolist(),bias=model[-1].bias.item())
    return dict(weights=model[0].weight.detach().flatten().tolist(),bias=model[0].bias.item())

def fit(data,steps):
    totals=frequency_table(data);keys=sorted(totals);ids={x:i for i,x in enumerate(keys)}
    x=torch.tensor(keys,dtype=torch.float64)/8.
    labels=torch.tensor([totals[k] for k in keys],dtype=torch.float64)
    idx,owners,n,y,quotas=contested(data,ids);assert len(quotas) and (y>0).any()
    policies={}
    for seed in (1703,1709):
        for hidden in (0,8):
            for objective in ('bce','quota'):
                torch.manual_seed(seed)
                model=(nn.Sequential(nn.Linear(12,hidden),nn.Tanh(),nn.Linear(hidden,1))
                       if hidden else nn.Sequential(nn.Linear(12,1))).double()
                opt=torch.optim.Adam(model.parameters(),lr=.04)
                for _ in range(steps):
                    logits=model(x).flatten()
                    regularizer=.001*sum(w.square().sum() for w in model.parameters())/sum(w.numel() for w in model.parameters())
                    if objective=='bce':
                        loss=(labels[:,0]*nn.functional.softplus(logits)+labels[:,1]*nn.functional.softplus(-logits)).sum()/labels.sum()
                    else:
                        scores=logits[idx]
                        grad=marginal_derivative(scores.detach(),owners,n,y,quotas)
                        # Exact gradient of the negative expected additive paired return.
                        loss=-(scores*grad).sum()
                    opt.zero_grad();(loss+regularizer).backward();opt.step()
                policies[f'{objective}-{hidden}-{seed}']=export(model,hidden)
    return dict(donors=[d['case'] for d in data],inputs=12,steps=steps,distinct_inputs=len(totals),
        training_lanes=int(labels.sum()),training_births=int(labels[:,1].sum()),
        contested_groups=len(quotas),contested_grants=int(quotas.sum()),models=policies)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('data',type=Path);parser.add_argument('out',type=Path)
    parser.add_argument('--steps',type=int,default=140)
    args=parser.parse_args();torch.set_num_threads(1)
    data=[json.loads((args.data/(c+'.json')).read_bytes()) for c in DONORS]
    result=fit(data,args.steps);args.out.write_text(json.dumps(result,indent=1)+'\n')
    print(result['training_lanes'],result['training_births'],result['contested_groups'],flush=True)
