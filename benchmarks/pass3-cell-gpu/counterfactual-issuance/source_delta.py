"""Fit a finite issuance decision from random pivot and keyed-function snapshots."""
import random
from itertools import product

import torch


def samples(seed, pages, only_new):
    rng=random.Random(seed)
    inputs,labels=[],[]
    for _ in range(pages):
        watermark=rng.randrange(1,10)
        table={k:rng.randrange(watermark+3) for k in range(16) if rng.random()<.65}
        for _ in range(12):
            key=rng.randrange(16)
            version=rng.randrange(watermark+3) if not only_new else watermark
            other=table.get(key)
            inputs.append([other is not None, version>=watermark, other is not None and other>=watermark])
            labels.append(other is not None and max(version,other)>=watermark)
    return torch.tensor(inputs,dtype=torch.float),torch.tensor(labels,dtype=torch.float)


def train(device):
    held_x,held_y=samples(55021,256,False)
    lanes=torch.tensor(list(product((0.,1.),repeat=3)))
    report={}
    for name,width,pages,steps,only_new in (
            ("only_new",8,128,160,True),("short",8,128,2,False),
            ("small",8,3,160,False),("mixed",8,128,160,False),("wide",32,128,160,False)):
        torch.manual_seed(5513)
        x,y=(t.to(device) for t in samples(5513,pages,only_new))
        net=torch.nn.Sequential(torch.nn.Linear(3,width),torch.nn.Tanh(),torch.nn.Linear(width,1)).to(device)
        opt=torch.optim.Adam(net.parameters(),lr=.04)
        for _ in range(steps):
            opt.zero_grad()
            torch.nn.functional.binary_cross_entropy_with_logits(net(x).flatten(),y).backward()
            opt.step()
        net.cpu().eval()
        with torch.no_grad():
            actions=(net(lanes).flatten()>0).tolist()
            # A missing function row cannot have a fresh version. These two
            # impossible input codes never occur in the issuer.
            actions[1]=actions[3]=False
            test=(net(held_x).flatten()>0)
            report[name]=dict(false_reject=int((~test & held_y.bool()).sum()),
                              false_issue=int((test & ~held_y.bool()).sum()),actions=actions)
    return dict(seed=5513,test_seed=55021,test_rows=len(held_y),device=device,arms=report,tests=fit_tests(device))


def fit_tests(device):
    import operator
    ops=(operator.eq,operator.lt,operator.le,operator.gt,operator.ge)
    rng=random.Random(5523)
    rows=[]
    for _ in range(1024):
        op=rng.randrange(len(ops))
        a=rng.randrange(-128,129)
        delta=rng.choice((-1,0,1)) if rng.random()<.4 else rng.randrange(-128,129)
        b=a+delta
        rows.append((op,(a>b)-(a<b)+1,ops[op](a,b)))
    def inputs(rows):
        return torch.tensor([[float(i==op) for i in range(5)]+[float(i==order) for i in range(3)]
                             for op,order,*_ in rows],device=device)
    lanes=[(op,order) for op in range(5) for order in range(3)]
    report={}
    distinct=[r for r in rows if r[1]!=1]
    while len(distinct)<len(rows):
        op=rng.randrange(len(ops))
        a=rng.randrange(-128,129)
        b=a+rng.choice((-1,1))*rng.randrange(1,129)
        distinct.append((op,(a>b)-(a<b)+1,ops[op](a,b)))
    for name,data in (("distinct",distinct),("ties",rows)):
        torch.manual_seed(5523)
        model=torch.nn.Sequential(torch.nn.Linear(8,12),torch.nn.Tanh(),torch.nn.Linear(12,1)).to(device)
        x=inputs(data)
        y=torch.tensor([float(r[-1]) for r in data],device=device)
        opt=torch.optim.Adam(model.parameters(),lr=.04)
        for _ in range(160):
            opt.zero_grad()
            torch.nn.functional.binary_cross_entropy_with_logits(model(x).flatten(),y).backward()
            opt.step()
        with torch.no_grad():
            scores=(model(inputs(lanes)).flatten()>0).cpu().tolist()
        seen={(op,order) for op,order,_ in data}
        actions=[score if lane in seen else True for score,lane in zip(scores,lanes)]
        if any(not keep and ops[op](order,1) for keep,(op,order) in zip(actions,lanes)):
            raise ValueError("unsafe local test readout")
        report[name]=dict(actions=actions, examples=len(data), observed_lanes=len(seen))
    return report
