"""Keep same-snapshot address accuracy distinct from actual search-free model rollouts."""
import argparse
from collections import Counter
import hashlib
from itertools import permutations
import json
import random
from pathlib import Path
import subprocess
from time import perf_counter

import torch
from rule_read import load_actor
from catalog import KINDS, Catalog
from history import stream
from online import execute,propose


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(targets,proposals):
    """One-to-one maximum exact token credit, then match individual parent roles."""
    n=max(len(proposals),len(targets))
    def credit(t,p):
        if t is None or p is None or t[0]!=p[0]:
            return 0,0
        return int(t==p),sum(a==b for a,b in zip(t[1],p[1],strict=True))
    if n>6:
        # Offline metric only. One exact certificate outweighs all possible
        # individual-role matches in the whole alignment.
        import networkx as nx
        graph=nx.Graph()
        bonus=1+sum(len(t[1]) for t in targets)
        for i,t in enumerate(targets):
            for j,p in enumerate(proposals):
                exact,roles=credit(t,p)
                if exact or roles:
                    graph.add_edge(i,len(targets)+j,weight=bonus*exact+roles)
        paired={}
        for u,v in nx.max_weight_matching(graph):
            i,j=sorted((u,v))
            paired[i]=proposals[j-len(targets)]
        return [(t,paired.get(i)) for i,t in enumerate(targets)]
    pred=proposals+[None]*(n-len(proposals))
    target=targets+[None]*(n-len(targets))
    def score(order):
        pairs=[credit(t,pred[j]) for t,j in zip(target,order)]
        return sum(x for x,_ in pairs),sum(y for _,y in pairs)
    order=max(permutations(range(n)),key=score)
    return [(t,pred[j]) for t,j in zip(target,order) if t is not None]


def assess(root,binary,weights,seed, field_pointer=False, splits=None, snapshot_count=None):
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    actor = load_actor(weights, field_pointer)
    numbers = b''.join(t.detach().numpy().tobytes() for t in actor.state_dict().values())
    result=dict(snapshot_receipts='unavailable',exclusive_live_receipts=getattr(actor,'requires_receipts',False),
                field_pointer=field_pointer,provider='trained' if weights else 'random_initialization',seed=seed,
                build_sha256=sha(binary.read_bytes()),weights_sha256=sha(numbers),device='single-thread CPU',
                snapshot_metric='address equality to one reference certificate; each proposal used at most once',
                exclusive_credit='common complete Run prefix lower bound; divergent suffix is uncredited',splits={})
    manifest=json.loads((root/'manifest.json').read_bytes())
    known=set(r['split'] for r in manifest)
    if splits and set(splits)-known:
        raise ValueError('unknown evaluation split')
    if snapshot_count is not None and snapshot_count<1:
        raise ValueError('snapshot budget must be positive')
    result['snapshot_budget_per_case']=snapshot_count
    for split in dict.fromkeys(splits or [r['split'] for r in manifest]):
        cases=[]
        totals=Counter()
        correct,required=Counter(),Counter()
        for case in (c for c in manifest if c['split']==split):
            path=root/case['directory']
            case_seed=seed+case['seed']
            selected=None
            if snapshot_count is not None:
                runs=case['runs']
                selected=set(random.Random(case_seed).sample(range(1,runs+1),min(snapshot_count,runs)))
            with torch.no_grad():
                nodes=None
                for cat,s in stream(path,case_seed,selected,getattr(actor,'catalog_type',Catalog)):
                    if nodes is None:
                        nodes=actor.template_graph(cat)
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
        result['splits'][split]=dict(programs=len(cases),families=sorted({c['merge_family'] for c in manifest if c['split']==split and 'merge_family' in c}),
            shadow=dict(mode='shadow',**totals,
                        complete_coverage=totals['correct_complete']/totals['teacher_commits'] if totals['teacher_commits'] else None,
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
    parser.add_argument('--split',action='append')
    parser.add_argument('--snapshot-count',type=int)
    a=parser.parse_args()
    a.output.write_text(json.dumps(assess(a.corpus,a.receiver.resolve(),a.weights,a.seed,a.field_pointer,a.split,a.snapshot_count),indent=2)+'\n')
