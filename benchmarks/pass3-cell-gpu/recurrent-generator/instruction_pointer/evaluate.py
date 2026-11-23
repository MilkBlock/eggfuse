"""Keep same-snapshot address accuracy distinct from actual search-free model rollouts."""
import argparse
from collections import Counter
import hashlib
from itertools import permutations
import json
from pathlib import Path
import subprocess
from time import perf_counter

import torch
from actor import InstructionActor
from catalog import KINDS
from history import load
from online import execute,propose


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(targets,proposals):
    """One-to-one maximum exact token credit, then match individual parent roles."""
    n=max(len(proposals),len(targets))
    if n>6:
        raise ValueError('exact lane assignment for this small ablation supports at most six targets')
    def credit(t,p):
        if t is None or p is None or t[0]!=p[0]:
            return 0,0
        return int(t==p),sum(a==b for a,b in zip(t[1],p[1],strict=True))
    pred=proposals+[None]*(n-len(proposals))
    target=targets+[None]*(n-len(targets))
    def score(order):
        pairs=[credit(t,pred[j]) for t,j in zip(target,order)]
        return sum(x for x,_ in pairs),sum(y for _,y in pairs)
    order=max(permutations(range(n)),key=score)
    return [(t,pred[j]) for t,j in zip(target,order) if t is not None]


def assess(root,binary,weights,seed, field_pointer=False):
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    actor=InstructionActor(field_pointer=field_pointer).eval()
    if weights:
        actor.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True))
    numbers = b''.join(t.detach().numpy().tobytes() for t in actor.state_dict().values())
    result=dict(field_pointer=field_pointer,provider='trained' if weights else 'random_initialization',seed=seed,
                build_sha256=sha(binary.read_bytes()),weights_sha256=sha(numbers),device='single-thread CPU',
                snapshot_metric='address equality to one reference certificate; each proposal used at most once',
                exclusive_credit='common complete Run prefix lower bound; divergent suffix is uncredited',splits={})
    manifest=json.loads((root/'manifest.json').read_bytes())
    for split in dict.fromkeys(r['split'] for r in manifest):
        cases=[]
        totals=Counter()
        correct,required=Counter(),Counter()
        for case in (c for c in manifest if c['split']==split):
            path=root/case['directory']
            cat,frames=load(path,seed+case['seed'])
            with torch.no_grad():
                nodes=actor.template_graph(cat)
                for s in frames:
                    start=perf_counter()
                    proposed=propose(actor,cat,s,nodes)
                    totals['snapshot_network_seconds']+=perf_counter()-start
                    totals['snapshot_calls']+=1
                    totals['teacher_commits']+=len(s.targets)
                    totals['proposed']+=len(proposed)
                    totals['duplicates']+=len(proposed)-len(set(proposed))
                    totals['correct_complete']+=len(set(proposed)&set(s.targets))
                    totals['off_reference_unique']+=len(set(proposed)-set(s.targets))
                    kind={p.address:p.kind for p in s.ports}
                    for t,p in align(s.targets,proposed):
                        for i,a in enumerate(t[1]):
                            required[kind[a]]+=1
                            if p and p[0]==t[0] and p[1][i]==a:
                                correct[kind[a]]+=1
            native=json.loads(subprocess.check_output([binary,'reference',path/'program.json','-','audit']))
            run=execute(binary,path/'program.json',actor,seed+case['seed'])
            if native['state_sha']!=case['state_sha']:
                raise ValueError('reference changed')
            prefix=0
            for i,(a,b) in enumerate(zip(native['rhs'],run.pop('rhs_by_run'))):
                if a!=b or native['writes'][i]!=run['writes_by_run'][i] or native['schedule'][i]!=run['source_schedule'][i]:
                    break
                prefix+=native['schedule'][i][4]
            del run['writes_by_run'],run['source_schedule']
            run.update(case=case['directory'],reference_commits=native['matches'],
                       reference_runs=native['runs'],reference_seconds=native['seconds'],
                       reference_state_equal=run['state_sha']==native['state_sha'],
                       certified_reference_prefix_commits=prefix)
            cases.append(run)
        if not all(required[k]>0 for k in KINDS):
            raise ValueError('empty class in the reference set')
        result['splits'][split]=dict(programs=len(cases),families=sorted({c['merge_family'] for c in manifest if c['split']==split}),
            shadow=dict(mode='shadow',**totals,
                        complete_coverage=totals['correct_complete']/totals['teacher_commits'],
                        by_parent_kind={k:{'correct':correct[k],'required':required[k]} for k in KINDS}),
            exclusive=dict(mode='exclusive',complete_programs=sum(c['reference_state_equal'] for c in cases),
                           accepted=sum(c['counts']['accepted'] for c in cases),
                           reference_commits=sum(c['reference_commits'] for c in cases),
                           certified_reference_prefix_commits=sum(c['certified_reference_prefix_commits'] for c in cases),
                           runtime_event_proposals_charged_to_model=0,cases=cases))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path)
    parser.add_argument('receiver',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--weights',type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    parser.add_argument('--field-pointer',action='store_true')
    a=parser.parse_args()
    a.output.write_text(json.dumps(assess(a.corpus,a.receiver.resolve(),a.weights,a.seed,a.field_pointer),indent=2)+'\n')
