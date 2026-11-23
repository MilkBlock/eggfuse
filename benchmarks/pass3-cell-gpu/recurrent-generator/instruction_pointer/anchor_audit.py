"""Compare exclusive trajectories, and inspect the actual proposals on the first differing Run."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import torch

from mixed_results import exclusive, read
from online import execute
from rule_read import load_actor


def audit(root, binary, weights, wave_limit=1):
    torch.set_num_threads(1)
    model = load_actor(weights, True)
    report = dict(mode='exclusive', wave_limit=wave_limit, weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                  verifier_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), cases={})
    manifest = read(root/'manifest.json')
    cases = {r['directory']:1703+r['seed'] for r in manifest if r['split']=='held_eggcc'}
    cases['sum-divisors'] = 1703
    for name,seed in cases.items():
        path = root/name
        native = read(path/'capture.json')
        replay = json.loads(subprocess.check_output([binary,'replay',path/'program.json',path/'tape.json','audit']))
        if (any(native[k] != replay[k] for k in ('state_sha','schedule','rhs','writes','resumes','events'))
                or replay['unused'] or replay['counts']['accepted'] != native['matches']
                or replay['counts']['rejected'] or replay['counts']['duplicates']):
            raise ValueError('reference replay does not match')
        issuance = []
        def observe(run, proposals):
            if run != len(issuance)+1:
                raise ValueError('source Run missing')
            issuance.append(dict(by_rule=Counter(r for r,_ in proposals), distinct=len(set(proposals))))
        online = execute(binary,path/'program.json',model,seed,wave_limit=wave_limit,observe_proposals=observe)
        prefix = 0
        same_runs = 0
        for i,(rhs, actual) in enumerate(zip(native['rhs'],online['rhs_by_run'])):
            if rhs != actual or native['schedule'][i] != online['source_schedule'][i] or native['writes'][i] != online['writes_by_run'][i]:
                break
            prefix += native['schedule'][i][4]
            same_runs += 1
        first = same_runs+1
        gap = None
        if first <= max(len(issuance),len(native['rhs'])):
            refs = [p for p in read(path/'tape.json')['requests'] if p['run']==first]
            actual = online['source_schedule']
            gap = dict(run=first, actual_commits=actual[same_runs][4] if same_runs<len(actual) else None,
                       teacher_by_rule=Counter(r['rule'] for r in refs),
                       teacher_parent_counts=Counter(len(r['parents']) for r in refs),
                       issued=issuance[same_runs] if same_runs<len(issuance) else None)
        online.update(case=name, reference_runs=native['runs'],reference_commits=native['matches'],
                      reference_seconds=native['seconds'],reference_state_equal=native['state_sha']==online['state_sha'],
                      certified_reference_prefix_commits=prefix)
        report['cases'][name] = dict(first_difference=gap,common_runs=same_runs,exclusive=exclusive([online]))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','receiver','weights','output'):
        p.add_argument(key,type=Path)
    p.add_argument('--wave-limit',type=int,default=1)
    args=p.parse_args()
    args.output.write_text(json.dumps(audit(args.root,args.receiver,args.weights,args.wave_limit),indent=2)+'\n')
