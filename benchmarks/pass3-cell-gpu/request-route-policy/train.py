"""Fit signed measured returns or their exact two-action policy expectation in PyTorch."""
import argparse,json
from pathlib import Path
from statistics import median
import torch
from torch import nn


def fit(path,out):
    train=json.loads(path.read_bytes())
    assert {r['program'] for r in train}=={'sum-bits','dot-product','jacobi-1d'}
    x=torch.tensor([r['x'] for r in train],dtype=torch.float32)
    reward=torch.tensor([median(r['original_ns'])-median(r['request_ns']) for r in train],dtype=torch.float32)
    y=reward/reward.abs().mean().clamp_min(1.)
    result={}
    for seed in (1703,1709):
        for size in (0,8):
            for loss in ('bandit','return'):
                torch.manual_seed(seed)
                model=nn.Sequential(nn.Linear(8,size),nn.Tanh(),nn.Linear(size,1)) if size else nn.Sequential(nn.Linear(8,1))
                opt=torch.optim.Adam(model.parameters(),lr=.02)
                for i in range(250):
                    z=model(x).flatten()
                    reg=sum(w.square().sum() for w in model.parameters())/sum(w.numel() for w in model.parameters())
                    objective=-(z.sigmoid()*y).mean() if loss=='bandit' else (z-y).square().mean()
                    opt.zero_grad();(objective+.003*reg).backward();opt.step()
                head=model[-1]
                weights=dict(hidden=model[0].weight.detach().tolist() if size else [],
                             bias=model[0].bias.detach().tolist() if size else [],
                             output=head.weight.detach().flatten().tolist(),offset=head.bias.item())
                use=model(x).detach().flatten()>0
                result[f'{loss}-{size}-{seed}']=dict(weights=weights,params=sum(w.numel() for w in model.parameters()),
                    selected=int(use.sum()),total=len(use),train_us=float(reward[use].sum())/1000)
    out.write_text(json.dumps(result,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('labels',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();torch.set_num_threads(1);fit(a.labels,a.out)
