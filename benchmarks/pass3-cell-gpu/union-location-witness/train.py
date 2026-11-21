"""Train a shared binary head for every proposed Cell fact field from disjoint workloads."""
import argparse,json
from pathlib import Path
import torch
from torch import nn


def train(data):
    rows=[v for d in data.values() for v in d['features']]
    x=torch.tensor([v[0] for v in rows],dtype=torch.float32)/8
    counts=torch.tensor([v[1] for v in rows],dtype=torch.float32)
    n,p=counts.sum(dim=0);assert n>0 and p>0
    net=nn.Linear(x.shape[1],1);nn.init.zeros_(net.weight);nn.init.zeros_(net.bias)
    opt=torch.optim.Adam(net.parameters(),lr=.04)
    for _ in range(350):
        score=net(x).flatten()
        # Balance the observed source positives and negatives; calibrate precision versus recall separately.
        loss=(nn.functional.softplus(score)*counts[:,0]).sum()/n+(nn.functional.softplus(-score)*counts[:,1]).sum()/p
        loss+=.001*net.weight.square().mean()
        opt.zero_grad();loss.backward();opt.step()
    scores=net(x).detach().flatten()
    out=dict(weights=net.weight.detach().flatten().tolist(),bias=net.bias.item(),
             training_cases=list(data),positive=int(p),negative=int(n),thresholds={})
    for name,beta in [('strict',.5),('broad',2.)]:
        best=(-1.,0.)
        for t in torch.unique(scores):
            # Midway between distinct logits avoids backend rounding selecting ties differently.
            lower=scores[scores<t]
            cut=(t.item()+float(lower.max()))*.5 if len(lower) else t.item()-1.
            yes=scores>cut
            tp=float(counts[yes,1].sum());fp=float(counts[yes,0].sum());fn=float(p)-tp
            quality=(1+beta**2)*tp/max((1+beta**2)*tp+fp+beta**2*fn,1.)
            if (quality,cut)>best:best=(quality,cut)
        out['thresholds'][name]=best[1]
    return out

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('data',type=Path);a.add_argument('out',type=Path);a=a.parse_args()
    torch.set_num_threads(1)
    v=train(json.loads(a.data.read_bytes()));a.out.write_text(json.dumps(v,indent=1)+'\n')
    print(v['positive'],v['negative'],v['thresholds'])
