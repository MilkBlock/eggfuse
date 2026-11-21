"""Fit a single CPU logistic group gate on native post-commit donor outcomes only."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import torch

p=ArgumentParser(description=__doc__);p.add_argument('donors',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
raw=json.loads(a.donors.read_bytes());assert set(raw)=={'sum-bits','dot-product'}
X=[];Y=[];N=[]
for v in raw.values():
    for x,y,n in v['capture']['examples']:
        X.append(x);Y.append(y);N.append(n)
features=torch.tensor(X,dtype=torch.float64);target=torch.tensor(Y,dtype=torch.float64);weights=torch.tensor(N,dtype=torch.float64)
assert len(X) and weights.sum()>0
head=torch.zeros(3,dtype=torch.float64,requires_grad=True)
opt=torch.optim.LBFGS([head],line_search_fn='strong_wolfe',max_iter=60,tolerance_grad=1e-11)
def loss():
    opt.zero_grad()
    # Equal class mass controls abstention on both productive and unproductive
    # donors. The receiver independently authenticates every selected action.
    mass=weights/torch.where(target.bool(),weights[target.bool()].sum().clamp_min(1),weights[~target.bool()].sum().clamp_min(1))
    risk=(mass*torch.nn.functional.binary_cross_entropy_with_logits(features@head,target,reduction='none')).sum()+.01*head.square().sum()
    risk.backward();return risk
opt.step(loss)
report=dict(donors=sorted(raw),raw_sha256=sha256(a.donors.read_bytes()).hexdigest(),weights=head.detach().tolist(),
    features=['one','log learned bucket cardinality','log1p receiver table length / 8'],positive=int((weights*target).sum()),negative=int((weights*(1-target)).sum()),
    classes='at least one original source-committed lane',admit_threshold=0)
a.out.write_text(json.dumps(report,indent=1)+'\n');print(report)
