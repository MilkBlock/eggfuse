"""Select one or two batches of compiled page programs using real forced native returns."""
import argparse,json
import cProfile  # Load stdlib profile before research drivers add their profile.py directory.
from pathlib import Path
from statistics import median
from driver import configure,source,base,route

CASES=('sum-bits','dot-product','jacobi-1d')


def capture(a,previous,cases=CASES):
    data={}
    for name in cases:
        program,plans,req=configure(a,name);common=base(req)
        common['multi_mode']='profile'+common['multi_mode']
        all_shapes={s[0] for s in a.shapes if s}
        samples=[]
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as exact:gold=exact({})
        with source.base.session(a.native,program,plans) as infer:
            for lap in range(a.repeats+1):
                costs={}
                for arm,selected in ([('base',previous),('expanded',all_shapes)] if lap%2 else [('expanded',all_shapes),('base',previous)]):
                    v=infer(route(common,a.shapes,selected))
                    assert v['state_sha']==gold['state_sha'] and v['multi']['total_rhs']==gold['rhs_count'] and v['runs']==gold['runs']
                    costs[arm]=v['multi']['rule_profile']
                if lap:samples.append(costs)
        agg={}
        for rid,shape in enumerate(a.shapes):
            if shape is None or shape[0] in previous:continue
            key,x=shape
            counts=[s['base'][rid]['calls'] for s in samples]
            if not counts[0]:continue
            group=agg.setdefault(key,dict(x=x,calls=0,original=[0.]*a.repeats,expanded=[0.]*a.repeats))
            group['calls']+=counts[0]
            for i,s in enumerate(samples):
                p=s['base'][rid];q=s['expanded'][rid]
                assert p['calls']==q['calls']==counts[0] and p['raw']==q['raw']
                for dst,v in [('original',p),('expanded',q)]:
                    group[dst][i]+=sum(v[c] for c in ('frame_ms','issuance_ms','validation_ms'))
        data[name]=agg
    return data


def ranking(data):
    gains={};support={}
    for program in data.values():
        for k,v in program.items():
            support[k]=support.get(k,0)+1
            gains[k]=gains.get(k,0.)+median(a-b for a,b in zip(v['original'],v['expanded']))
    return sorted((k for k in gains if support[k]>=2 and gains[k]>0),key=lambda k:(-gains[k],k))


def heads(data,universe):
    import torch
    from torch import nn
    torch.set_num_threads(1)
    rows=[v for group in data.values() for v in group.values()]
    x=torch.tensor([r['x'] for r in rows],dtype=torch.float32)
    y=torch.tensor([median(a-b for a,b in zip(r['original'],r['expanded']))/r['calls'] for r in rows],dtype=torch.float32)
    weight=torch.tensor([r['calls'] for r in rows],dtype=torch.float32);weight/=weight.mean()
    y/=((weight*y.abs()).mean().clamp_min(1e-9))
    keys=sorted(universe);features=torch.tensor([universe[k] for k in keys],dtype=torch.float32)
    out={}
    for seed in (1703,1709):
        for h in (0,8):
            torch.manual_seed(seed);m=nn.Sequential(nn.Linear(8,h),nn.Tanh(),nn.Linear(h,1)) if h else nn.Sequential(nn.Linear(8,1))
            opt=torch.optim.Adam(m.parameters(),lr=.02)
            for _ in range(200):
                pred=m(x).flatten();reg=sum(p.square().sum() for p in m.parameters())/sum(p.numel() for p in m.parameters())
                loss=((pred-y).square()*weight).mean()+.003*reg
                opt.zero_grad();loss.backward();opt.step()
            gain=m(features).detach().flatten().tolist()
            out[f'return-{h}-{seed}']=dict(members=[k for k,v in zip(keys,gain) if v>0],
                weights={k:v.detach().tolist() for k,v in m.state_dict().items()},params=sum(p.numel() for p in m.parameters()))
    return out


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    one=capture(a,set());(a.out/'round1.json').write_text(json.dumps(one,separators=(',',':'))+'\n')
    rank=ranking(one);first=rank[:8]
    two=capture(a,set(first));(a.out/'round2.json').write_text(json.dumps(two,separators=(',',':'))+'\n')
    second=ranking(two)[:8]
    assert not set(first)&set(second)
    universe={v[0]:v[1] for v in a.shapes if v}
    policies={'first':dict(members=first),'one-pass':dict(members=rank[:16]),'iterated':dict(members=first+second)}
    policies.update(heads(one,universe))
    res=dict(training=list(CASES),round1=one,round2=two,policies=policies,universe=len(universe),features=universe)
    (a.out/'learning.json').write_text(json.dumps(res,separators=(',',':'))+'\n')
    print('Eligible shapes',len(universe),'first/extra',(len(first),len(second)),'overlap',len(set(first+second)&set(rank[:16])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=5)
    run(p.parse_args())
