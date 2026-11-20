"""Learn tied refinement bits from source-checked false positive pairs of the original head."""
import argparse
import cProfile  # Load the standard library profiler before importing the benchmark profile helpers.
import json
from pathlib import Path
import subprocess
import numpy as np
import torch
from common import base,configured,TRAIN


def collect(a):
    a.out.mkdir(parents=True,exist_ok=False);records={}
    cpu=a.exp/'compact-vanilla-20261121'
    for case in TRAIN:
        prog,plan,req=configured(a,case)
        with base.session(cpu/'vanilla-audit',prog) as source:gold=source({'audit':True})
        with base.session(a.build/'session',prog,plan) as infer:
            out=infer(dict(req,audit=True,capture_collisions=True));assert base.summarize(out,gold)['aligned']
        hard=out['multi']['hard_pairs'];stats=out['multi']['atom_constraints']
        hard['failures']=out['multi']['counts']['raw_parent_rejects']
        assert sum(n for _,_,n in hard['pairs'])+hard['alias']+hard['omitted']==hard['failures']-stats['failure_header']
        records[case]=hard
    (a.out/'training-pairs.json').write_text(json.dumps(records,separators=(',',':'))+'\n')
    return records


def bits(words):
    return (((words[:,None]>>torch.arange(16))&1).float()*2)-1


def train(a,records):
    frequencies={}
    for rec in records.values():
        for l,r,n in rec['pairs']:frequencies[l,r]=n+frequencies.get((l,r),0)
    keys=np.array(sorted(frequencies));counts=np.array([frequencies[tuple(q)] for q in keys]);probs=counts/counts.sum()
    torch.set_num_threads(1);report={}
    for width,recipe in ((2,'initial'),(2,'uniform'),(2,'hard'),(4,'hard'),(8,'hard')):
        torch.manual_seed(a.seed);rng=np.random.default_rng(a.seed)
        head=torch.nn.Linear(16,width,bias=False)
        opt=torch.optim.Adam(head.parameters(),lr=.01)
        for step in range(0 if recipe=='initial' else a.updates):
            # Salted words are features, not source addresses. Tying both sides preserves equal pairs.
            pair=rng.integers(0,1<<16,size=(256,2),dtype=np.int64)
            if recipe=='hard':
                pair[:192]=keys[rng.choice(len(keys),size=192,p=probs)]
            x,z=bits(torch.from_numpy(pair[:,0].copy())),bits(torch.from_numpy(pair[:,1].copy()))
            q,k=(head(x)*2).tanh(),(head(z)*2).tanh()
            collision=((1+q*k)*.5).prod(-1).mean()
            loss=collision+.05*(q.mean(0).square().mean()+k.mean(0).square().mean())
            opt.zero_grad();loss.backward();opt.step()
        weights=head.weight.detach()
        # Inactive output dimensions are hard zero, so the native >0 bit test leaves them clear.
        matrix=torch.cat([weights,torch.zeros(10-width,16)]).tolist()
        name=f'{recipe}{width}';path=a.out/f'{name}.json'
        path.write_text(json.dumps(dict(q=matrix,k=matrix,kind=recipe,bits=width,seed=a.seed))+'\n')
        subprocess.run([a.build/'bake',path,a.out/f'{name}.bin'],check=True)
        def signatures(words):
            return (head(bits(torch.from_numpy(words))).detach()>0).numpy()
        collision=(signatures(keys[:,0])==signatures(keys[:,1])).all(axis=1)
        report[name]=dict(bits=width,learned_coefficients=16*width,updates=0 if recipe=='initial' else a.updates,
                          paired_events=int(counts.sum()),unique_pairs=len(keys),remaining_training_collisions=int(counts[collision].sum()))
    (a.out/'training.json').write_text(json.dumps(report,indent=1)+'\n')
    print('Fitted heads',report,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','build','out'):p.add_argument(k,type=Path)
    p.add_argument('--updates',type=int,default=320);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--reuse-pairs', type=Path)
    a=p.parse_args()
    if a.reuse_pairs:
        a.out.mkdir(parents=True,exist_ok=False)
        data=json.loads(a.reuse_pairs.read_bytes());assert set(data)==set(TRAIN)
        (a.out/'training-pairs.json').write_bytes(a.reuse_pairs.read_bytes())
    else:data=collect(a)
    train(a,data)
