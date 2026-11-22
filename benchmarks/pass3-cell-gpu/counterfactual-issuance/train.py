"""Paired finite-action policy gradients at one real signed-block issuance."""
import argparse
import cProfile
import json
from pathlib import Path
import random
from runpy import run_path

import torch

here=Path(__file__).resolve().parent
block=run_path(str(here.parent/'ripsat-block-verifier/study.py'))
study=block['study']


def work(data):
    proof=data['strict_named']['set_publication']
    return dict(paid=study['packets'](data),headers=data['root_recipe']['root_header_checks'],
                capture_reads=proof['capture_row_reads'],admissions=proof['admissions'],
                checked_internal=proof['direct_binds'],completed=proof['completed_blocks'])


def verify(left,right):
    for k in ('rhs','writes','resumes','state_sha','schedule','runs','events'):
        if left[k]!=right[k]:
            raise ValueError(f'counterfactual changed {k}')
    if left['constructor_births']['endpoint']!=right['constructor_births']['endpoint']:
        raise ValueError('source identity changed')
    def semantic_roots(data):
        return [[r[0],*r[3:]] for r in data['root_recipe']['commits']]
    if semantic_roots(left)!=semantic_roots(right):
        raise ValueError('parent, version or output differed')


def train(a):
    program,plans,req,spec=study['setup'](argparse.Namespace(exp=a.exp,out=a.out.parent),'dot-product')
    weights=torch.nn.Parameter(torch.zeros(3,device=a.device))
    opt=torch.optim.Adam([weights],lr=.12)
    generator=random.Random(1703)
    records=[]
    with study['src'].base.session(a.native,program,plans) as run:
        for i in range(a.episodes):
            seed=29181+i
            rows=study['generated'](seed)
            def episode(force=None):
                actor=dict(mode='sample',weights=weights.detach().cpu().tolist(),seed=seed)
                if force is not None:
                    actor['force']=force
                config=study['matrix']['cfg'](req,dict(spec,issuance_actor=actor,
                                               block_verifier=True,receipt_scan=2),True)
                data=run(dict(config,generated_get_inputs=rows))
                if 'source_error' in data:
                    raise ValueError(data['source_error'])
                return data
            left=episode()
            decisions=left['strict_named']['issuance_actor']['decisions']
            if not decisions:
                continue
            index=generator.randrange(len(decisions))
            serial,x,selected=decisions[index]
            right=episode([serial,not selected])
            alternate=right['strict_named']['issuance_actor']['decisions']
            if decisions[:index]!=alternate[:index] or alternate[index]!=[serial,x,not selected]:
                raise ValueError('not the same prospective decision')
            verify(left,right)
            full,leaf=(work(left),work(right)) if selected else (work(right),work(left))
            gain={k:leaf[k]-full[k] for k in leaf}
            # Two distinct objectives: saved external decisions and receiver work.
            # Admission is charged even if its eventual continuation is stale.
            reward=gain['paid']+(gain['headers']+gain['capture_reads']+gain['admissions'])/8
            records.append(dict(seed=seed,index=index,serial=serial,x=x,full=full,leaf=leaf,
                                reward=reward))
            recent=records[-32:]
            features=torch.tensor([r['x'] for r in recent],device=a.device)
            returns=torch.tensor([r['reward'] for r in recent],device=a.device)
            loss=-(torch.sigmoid(features@weights)*returns).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    if not records or not any(r['reward']!=0 for r in records):
        raise ValueError('no informative paired decisions')
    a.out.write_text(json.dumps(dict(training_device=a.device,weights=weights.detach().cpu().tolist(),
                                     pairs=records),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','native','out'):
        parser.add_argument(name,type=Path)
    parser.add_argument('--device',choices=('cpu','mps'),default='mps')
    parser.add_argument('--episodes',type=int,default=128)
    train(parser.parse_args())
