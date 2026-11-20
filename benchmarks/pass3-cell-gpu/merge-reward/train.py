"""Equal-budget real/synthetic warm starts, followed by a matched real-feedback bandit update."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from synthetic import sample,check

ARMS=('prior','offer','settled','work','charged')
TRAIN=('affine-twins','clamped-ramp','segmented-prefix','window-laplacian')


def tensor(rows):
    return torch.tensor([r['features'] for r in rows]),torch.tensor([r['counts'] for r in rows],dtype=torch.float32)


def rewards(counts):
    encounters,fresh,won,rebuild=counts.T
    # At publication both execution paths retain the source RHS. Credit the unique child
    # only once; several scans of the same immutable port are distinct measured operations.
    assert ((won>=0)&(won<=1)&(fresh>=won)&(encounters>=fresh)).all()
    net=encounters-fresh-rebuild+fresh+fresh
    return {'prior':torch.zeros_like(won),'offer':torch.ones_like(won),'settled':won,'work':net}


def fit(native,out,seeds,updates,warm,families=TRAIN):
    check();out.mkdir(parents=True,exist_ok=False)
    corpus=json.loads(native.read_bytes());assert set(corpus)==set(TRAIN)
    assert set(families)<=set(TRAIN) and len(set(families))==len(families)
    actual=[r for n in families for r in corpus[n]['charges']]
    x,c=tensor(actual);rs=rewards(c)
    # Keep heterogeneous work units explicit. The two fresh terms are a root recheck and
    # a child packet separately. Global, unattributable frontier rebuilds are charged
    # in live evaluation. A local training advantage alone cannot establish net savings.
    scale=max(1.,float(rs['work'].abs().median()))
    charged=[]
    for name in families:
        d=corpus[name]
        owner=sum(r['counts'][3] for r in d['charges'])
        assert owner>0 and d['on_boundary'][1]>=owner
        price=d['on_boundary'][1]/owner
        for row in d['charges']:
            e,f,w,h=row['counts']
            charged.append(e-f+f+f-price*h)
        # Full selection is additive once; mixed gates are measured on the real executor.
        b=d['on_boundary']
        assert abs(sum(charged[-len(d['charges']):])-(b[2]-b[3]+b[6]+b[8]-b[1]))<1e-5
    rs['charged']=torch.tensor(charged)
    stats={'train_cases':families,'native_events':len(x),'native_child_wins':int(c[:,2].sum()),
           'work_scale':scale,'updates':updates,'warm':warm,'policies':{}}
    torch.set_num_threads(1)
    for seed in seeds:
        syn=sample(seed+157,1000);sx,sc=tensor(syn)
        stats.setdefault('synthetic',{})[seed]={'events':len(sc),'wins':int(sc[:,2].sum())}
        for distribution,xx,cc in [('real',x,c),('synthetic',sx,sc)]:
            def init():
                torch.manual_seed(seed)
                model=torch.nn.Linear(8,1)
                torch.nn.init.normal_(model.weight,std=.06);torch.nn.init.zeros_(model.bias)
                return model
            model=init();opt=torch.optim.Adam(model.parameters(),lr=.025)
            rng=torch.Generator().manual_seed(seed+11)
            for _ in range(warm):
                ids=torch.randint(len(xx),(96,),generator=rng)
                logits=model(xx[ids]).squeeze(1)
                loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,cc[ids,2])
                opt.zero_grad();loss.backward();opt.step()
            saved={k:p.detach().clone() for k,p in model.state_dict().items()}
            for arm in ARMS:
                model=init();model.load_state_dict(saved)
                opt=torch.optim.Adam(model.parameters(),lr=.025);rng=torch.Generator().manual_seed(seed+23)
                for _ in range(updates):
                    ids=torch.randint(len(x),(96,),generator=rng)
                    logit=model(x[ids]).squeeze(1);yes=logit.sigmoid()
                    common=torch.nn.functional.binary_cross_entropy_with_logits(logit,c[ids,2])
                    adv=rs[arm][ids]
                    if arm in ('work','charged'):adv=(adv/scale).clamp(-8.,8.)
                    # Exact expected return for the binary choice, no sampling variance.
                    loss=common-1.5*(yes*adv).mean()
                    opt.zero_grad();loss.backward();opt.step()
                gate={'weights':model.weight.detach().flatten().tolist(),'bias':model.bias.item(),'threshold':0.}
                v=(model(x).detach().flatten()>0)
                stats['policies'][f'{seed}-{distribution}-{arm}']=dict(gate=gate,selected=int(v.sum()),won=int(c[v,2].sum()))
    (out/'policies.json').write_text(json.dumps(stats,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('native',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709]);p.add_argument('--updates',type=int,default=120);p.add_argument('--warm',type=int,default=80)
    p.add_argument('--families',nargs='+',choices=TRAIN,default=TRAIN)
    a=p.parse_args();fit(a.native,a.out,a.seeds,a.updates,a.warm,a.families)
