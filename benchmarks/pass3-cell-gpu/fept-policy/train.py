"""Train a contextual class-action policy on full native proposal-count returns."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F

DONORS=("sum-bits","dot-product","jacobi-1d")
DTYPE=torch.float64


def export(model,mean,std):
    with torch.no_grad():
        w=model[0].weight/std
        b=model[0].bias-w@mean
        if len(model)==1:
            return {"direct":w[0].tolist(),"bias":b[0].item()}
        return {"hidden":w.tolist(),"offsets":b.tolist(),"output":model[2].weight[0].tolist(),
                "bias":model[2].bias[0].item()}


def fit(rows,objective,hidden,seed=1703):
    x=torch.tensor([r[2] for r in rows],dtype=DTYPE)
    n=torch.tensor([r[3] for r in rows],dtype=DTYPE)
    mean=x.mean(0)
    std=x.std(0,unbiased=False).clamp_min(.1)
    normalized=(x-mean)/std
    torch.manual_seed(seed)
    m=(nn.Sequential(nn.Linear(x.shape[1],hidden),nn.Tanh(),nn.Linear(hidden,1))
       if hidden else nn.Sequential(nn.Linear(x.shape[1],1))).to(DTYPE)
    opt=torch.optim.Adam(m.parameters(),lr=.025)
    difference=n-(2 if objective=="feedback" else 1)
    weight=difference.abs().mean().clamp_min(1.)
    for step in range(300):
        z=m(normalized).squeeze(1)
        prob=z.sigmoid()
        if objective=="terminal":
            y=torch.tensor([r[4]>0 for r in rows],dtype=DTYPE)
            loss=F.binary_cross_entropy_with_logits(z,y)
        elif objective=="bce":
            loss=F.binary_cross_entropy_with_logits(z,(n>1).to(DTYPE))
        elif objective=="reinforce":
            # Native graph state and coverage are arm-invariant. Sampling a
            # contextual action changes the return by n-1. Center the observed
            # reward on its conditional expectation to remove its large offset.
            with torch.no_grad():
                a=torch.bernoulli(prob)
                advantage=(a-prob)*difference
            log_action=-F.binary_cross_entropy_with_logits(z,a,reduction="none")
            loss=-(log_action*advantage).mean()/weight
        else:
            loss=-(prob*difference).mean()/weight
        l2=sum(w.square().mean() for w in m.parameters())
        opt.zero_grad()
        (loss+.0003*l2).backward()
        opt.step()
    w=export(m,mean,std)
    chosen=m(normalized).detach().flatten()>0
    if hidden:
        external=(x@torch.tensor(w["hidden"],dtype=DTYPE).T+torch.tensor(w["offsets"],dtype=DTYPE)).tanh()@torch.tensor(w["output"],dtype=DTYPE)+w["bias"]
    else:
        external=x@torch.tensor(w["direct"],dtype=DTYPE)+w["bias"]
    assert torch.equal(external>0,chosen)
    return w,dict(parameters=sum(p.numel() for p in m.parameters()),choices=len(rows),
                  selected=int(chosen.sum()),saved=int((chosen*(n-1)).sum()),
                  maximum_saved=int((n-1).clamp_min(0).sum()))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("data",type=Path);p.add_argument("out",type=Path)
    args=p.parse_args()
    torch.set_num_threads(1)
    rows=[];digests={}
    for case in DONORS:
        data=(args.data/(case+".json")).read_bytes();v=json.loads(data)
        assert v["case"]==case
        digests[case]=sha256(data).hexdigest();rows.extend(v["samples"])
    policies={};results={}
    for name,h in (("bce",0),("reward",0),("reward",8),("reinforce",8),("feedback",8),("terminal",8)):
        variant=f"{name}-{h}"
        policies[variant],results[variant]=fit(rows,name,h)
    args.out.write_text(json.dumps(dict(donor_sha=digests,seed=1703,models=policies,training=results),indent=1)+"\n")
    print(results,flush=True)
