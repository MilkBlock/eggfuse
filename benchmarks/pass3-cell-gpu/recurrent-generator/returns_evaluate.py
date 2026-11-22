"""Greedy before/after comparison on held-out source Runs, including exact residuals."""
import argparse
from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch
from capture import execute, inputs, load_catalog, read, verify
from chain_check import serial_compiler
from compound_model import compiled_actions
from fept import retained,measure,winning_proposals


def evaluate(a):
    torch.set_num_threads(1)
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    ref=a.exp/'pass3-release-reproduction-20261120'
    corpus=a.exp/'repair-bake-families-20261120'
    donor=ref/'sum-bits/program.json'
    for case in a.cases:
        image,program,gold=inputs(corpus,ref,case)
        entries=load_catalog(image,program,donor)
        scores={}
        before_winners=None
        for arm,checkpoint in [('supervised',a.before),('returns',a.after)]:
            model=read(checkpoint)
            if case in model['train']:
                raise ValueError('training workload in holdout')
            joins,tails,wires=compiled_actions(read(donor),model['three_step'])
            cfg=dict(catalog=entries,rows=2,ranks=8,hidden=8,waves=2,weights=model['roots'],
                     complete_residual=not a.no_exact,
                     compound=dict(joins=joins,tails=tails,wires=wires,batch=True,named_boundary=True,
                                   child=model['child']))
            dest=a.out/f'{case}-{arm}'
            with TemporaryDirectory() as tmp:
                execute(image/'device.json',a.exp/'rotary-axes-20261119/packed-1703/final.pt',
                        ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True,
                        serial_compile=serial_compiler(Path(tmp)),birth_audit=bool(a.source))
            if not a.no_exact:
                verify(dest,gold,image)
            role=read(dest/'run.json')
            counts=Counter()
            with np.load(dest/'neural-output.npz') as z,np.load(dest/'compound-output.npz') as c:
                issued=int((z['raw'][:,:,11]>0).sum())
                banks=[c['claims'],c['tails'],*[c[k] for k in c if k.startswith('hop_')]]
                for t,lane in np.argwhere(z['raw'][:,2:,11]>0):
                    action=int(banks[0][t,lane,1])
                    if tails[action]<0:continue
                    hop=0
                    while tails[action]>=0:
                        hop+=1
                        action=tails[action]
                    counts['composed']+=1
                    if banks[hop][t,lane,7]>0:counts['complete']+=1
            scores[arm]=dict(issued=issued,exact=role['execution_roles']['rhs_inputs_from_exact_search'],
                             proposed_rhs=role['execution_roles']['rhs_inputs_from_recurrent_neural_proposals'],
                             composed=counts['composed'],complete=counts['complete'],runs=role['completed'],
                             boundary=role['named_boundary'])
            if a.source:
                source = a.source / case
                births = retained(source,image)
                scores[arm]['strict'] = measure(dest,source,births)
                winners, _ = winning_proposals(dest)
                if before_winners is None:
                    before_winners = winners
                else:
                    lost = np.setdiff1d(before_winners,winners)
                    new = np.setdiff1d(winners,before_winners)
                    scores[arm]['visible_lost'] = int(births[lost].sum())
                    scores[arm]['visible_added'] = int(births[new].sum())
        report[case]=scores
        (a.out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
        print(case,scores,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','before','after','out'):p.add_argument(name,type=Path)
    p.add_argument('--cases',nargs='+',default=['histogram-scatter','gated-state','sum-bits'])
    p.add_argument('--no-exact',action='store_true')
    p.add_argument('--source',type=Path)
    evaluate(p.parse_args())
