"""Time the frozen higher-Cell policy with its audited signed operation counts."""
import argparse
import json
from pathlib import Path
from statistics import median

import torch
from assist_cost import measure
from higher_cell import digest, read, run


def compare(root, name, binary, weights, policy, audit_dir, seed, side_head=None):
    folder = root/name
    arms = ('closed','fork') if side_head is not None else ('base','owned')
    audits = {arm:read(audit_dir/f'{name}-{arm}.json') for arm in arms}
    spec = dict(binary=digest(binary),weights=digest(weights),program=digest(folder/'program.json'))
    if side_head and audits['fork']['side_weights'] != digest(side_head/'side.pt'):
        raise ValueError('effective operation audit used a different side pointer')
    for record in audits.values():
        if any(record[k]!=v for k,v in spec.items()):
            raise ValueError('effective operation audit needs the timed binary, program and weights')
    pairs = []
    for turn in range(4):
        order = ['exact',*arms,'oracle']
        if turn%2:
            order.reverse()
        trial = {}
        for arm in order:
            if arm in audits:
                current = run(folder,binary,weights,policy,seed,'owned' if side_head else arm,False,audit=False,
                              side_head=side_head if arm=='fork' else None,keep_closed=arm=='fork')['execution']
                wall = current['policy_process_wall']
                audited = audits[arm]['execution']
                for key in ('issued','counts','state_sha','higher','side_pointer','withheld_owned_requests'):
                    if current.get(key)!=audited.get(key):
                        raise ValueError('timed issuance differs in '+key)
                ept = audited['ept']
                signed = sum(ept['signed_external']) + sum(ept['signed_internal'])
                trial[arm] = dict(wall=wall,signed_operations=signed,ops_per_second=signed/wall,
                                  actor=current['network_seconds'],verify=current['native_verify_seconds'],
                                  residual=current['assist']['exact_seconds'])
            else:
                trial[arm] = measure(folder,binary,weights,seed,arm,False)
        pairs.append(trial)
    return dict(**spec, mode='complete native assist',pairs=pairs,
                median_wall={arm:median(r[arm]['wall'] for r in pairs) for arm in pairs[0]},
                median_signed_ops_per_second={arm:median(r[arm]['ops_per_second'] for r in pairs) for arm in audits})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','binary','weights','policy','audit','out'):
        p.add_argument(n,type=Path)
    p.add_argument('--side-head',type=Path)
    p.add_argument('--cases',required=True,nargs='+')
    a=p.parse_args()
    seeds={r['directory']:r['seed'] for r in read(a.root/'manifest.json')}
    torch.set_num_threads(1)
    for name in a.cases:
        result=compare(a.root,name,a.binary,a.weights,read(a.policy),a.audit,1703+seeds.get(name,0),a.side_head)
        (a.out/(name+'-density.json')).write_text(json.dumps(result,indent=2)+'\n')
