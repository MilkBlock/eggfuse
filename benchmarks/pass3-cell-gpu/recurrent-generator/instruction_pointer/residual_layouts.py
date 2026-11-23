"""Measure which live residual commits have an observed higher-Cell entry from a signed root."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from layout_credit import CreditIssuer
from online import INTERNAL, RESIDUAL, execute
from prefix_policy import Policy
from ripsat_layout import capture
from ripsat_replay import unpack
from train_layout_bandit import LearnedChoice

def collect(folder,donor,binary,weights,baked,policy,seed,trace):
    actor=load_actor(weights,True)
    issuer=CreditIssuer(actor,donor,read(folder/'program.json'),baked,omit=True,
                        explore=False,attach=True,seed=seed,policy=policy)
    trace.mkdir(parents=True,exist_ok=True)
    program=trace/'program.json'
    if not program.exists():
        program.symlink_to((folder/'program.json').resolve())
    if digest(program)!=digest(folder/'program.json'):
        raise ValueError('incompatible trace destination')
    requests=[]
    with (trace/'memory.jsonl').open('w') as frames, TemporaryDirectory() as tmp:
        spec=Path(tmp)/'layouts.json'
        spec.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
        def observe(frame):
            requests.extend(frame['accepted'])
            frames.write(json.dumps({k:frame[k] for k in ('run','updates','retired','rules')},
                                    separators=(',',':'))+'\n')
        run=execute(binary,program,actor,seed,assist=True,prefix_policy=Policy(32),
                    graph_issuer=issuer,layout_file=spec,frame_observer=observe)
    reference=read(folder/'capture.json')
    for actual,expected in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                            ('resume_audit','resumes'),('event_audit','events'),('state_sha','state_sha')]:
        if run[actual]!=reference[expected]:
            raise ValueError('source reference mismatch in '+expected)
    tokens={r['token'] for r in requests}
    residual=sum(t>=RESIDUAL for t in tokens)
    if (len(tokens)!=len(requests) or residual!=run['assist']['residual_commits'] or
        len(tokens)-residual!=run['counts']['accepted'] or len(tokens)!=reference['matches']):
        raise ValueError('sealed receipts differ from the native commit partition')
    (trace/'tape.json').write_text(json.dumps({'requests':requests},separators=(',',':')))
    return dict(program=digest(program),binary=digest(binary),actor=digest(weights),policy=policy.checkpoint,
                state_sha=run['state_sha'],accepted=run['counts']['accepted'],residual=residual,
                runs=run['runs'],network_seconds=run['network_seconds'],wall_seconds=run['wall_seconds'])


def analyze(trace,donor,catalog,limit):
    refs,_,roots,_=capture(trace,donor,limit,each_parent_first=True)
    covered=defaultdict(set)
    best=defaultdict(dict)
    layout_targets=defaultdict(set)
    for j,layouts in roots.items():
        root=refs[j]['token']
        if root>=RESIDUAL:
            continue
        for layout,occ in layouts.items():
            for boundary,ready,first,tokens in occ:
                targets={t for t in tokens[1:] if t>=RESIDUAL}
                covered['observed_subgraphs'].update(targets)
                if root<INTERNAL:
                    covered['external_observed'].update(targets)
                    if ready:
                        covered['external_ready_versions'].update(targets)
                    if first:
                        covered['external_first_schedule'].update(targets)
                if not targets or not ready or not first:
                    continue
                covered['ready_subgraphs'].update(targets)
                if root>=INTERNAL:
                    covered['ready_internal_entry'].update(targets)
                    continue
                covered['ready_external_entry'].update(targets)
                layout_targets[layout].update(targets)
                if layout in catalog:
                    covered['catalog_external_entry'].update(targets)
                    if len({slot for _,slot in layout[0][2]})==len(boundary):
                        covered['catalog_entire_boundary_in_root'].update(targets)
                    best[j][layout]=max(len(targets),best[j].get(layout,0))
    residual={r['token'] for r in refs if r['token']>=RESIDUAL}
    by_rule=Counter(r['rule'] for r in refs if r['token'] in residual-covered['ready_external_entry'])
    return dict(reach={k:len(covered[k]) for k in ('observed_subgraphs','ready_subgraphs',
                'ready_internal_entry','ready_external_entry','catalog_external_entry')},
                stages={k:len(covered[k]) for k in ('external_observed','external_ready_versions',
                        'external_first_schedule','catalog_entire_boundary_in_root')},
                residual_without_observed_ready_external=len(residual-covered['ready_external_entry']),
                new_layout_options=len(layout_targets.keys()-catalog),
                per_root_oracle_upper_bound=min(len(covered['catalog_external_entry']),
                    sum(max(choices.values()) for choices in best.values())),
                largest_uncovered_rules=by_rule.most_common(8)),layout_targets


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','baked','policy','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    donor=read(a.donor/'program.json')
    catalog=set(unpack(read(a.baked/'catalog.json')))
    policy=LearnedChoice(a.policy,a.baked)
    seeds={r['directory']:r['seed'] for r in read(a.root/'manifest.json')}
    for name in a.cases:
        trace=a.out/name
        native=collect(a.root/name,donor,a.binary,a.weights,a.baked,policy,
                       1703+seeds.get(name,0),trace)
        budget=max(map(len,catalog))
        report,_=analyze(trace,donor,catalog,budget)
        (trace/'opportunity.json').write_text(json.dumps(dict(native=native,**report,
            catalog=digest(a.baked/'catalog.json'),max_rules=budget),indent=2)+'\n')
