"""Separate layout and boundary selection by interventions on a fixed live assist history."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from anchor_set_audit import load_actor
from higher_cell import read
from layout_credit import CreditIssuer
from online import execute
from prefix_policy import Policy
from residual_layouts import INTERNAL, RESIDUAL
from ripsat_layout import capture
from ripsat_policy import root_context
from side_boundary import address
from train_layout_bandit import LearnedChoice


@torch.no_grad()
def audit(folder,trace,donor,binary,weights,base,baked,old,new,seed):
    actor=load_actor(weights,True)
    program=read(folder/'program.json')
    def issuer(path,policy):
        return CreditIssuer(actor,donor,program,path,seed=seed,attach=True,
                            omit=True,explore=False,policy=LearnedChoice(policy,path))
    live=issuer(base,old)
    probe=issuer(baked,new)
    lookup={l:i for i,l in enumerate(probe.layouts)}
    refs,_,roots,_=capture(trace,donor,max(map(len,lookup)),each_parent_first=True)
    runs=defaultdict(list)
    for j,layouts in roots.items():
        req=refs[j]
        if req['token']>=INTERNAL:
            continue
        candidates={}
        for layout,occ in layouts.items():
            u=lookup.get(layout)
            if u is None:
                continue
            for boundary,ready,first,tokens in occ:
                residual={t for t in tokens[1:] if t>=RESIDUAL}
                if ready and first and residual:
                    candidates.setdefault(u,defaultdict(set))[boundary].update(residual)
        if candidates:
            runs[req['run']].append((req,candidates))
    proven=defaultdict(set)
    counts=Counter()
    receipts=[]
    context_groups=defaultdict(list)
    def snapshot(catalog,history,snap):
        if snap.run not in runs:
            return
        domains=defaultdict(list)
        for port in snap.ports:
            domains[port.table].append(port)
        for req,targets in runs[snap.run]:
            eligible=[u for u in probe.choices[req['rule']] if all(
                probe.rule[probe.layouts[u][i][0]] in snap.rules for i in probe.groups[u][0])]
            if not targets.keys()<=set(eligible):
                raise ValueError('observed graph is not eligible at the root')
            fields=[tuple(history.visible[address(p)]['hashes']) for p in req['parents']]
            context=root_context(fields,actor.width)
            selected=probe.choose_layout(req,eligible,context)
            observed={}
            reproduced={}
            counts['roots']+=1
            counts['roots_selecting_observed_target']+=selected in targets
            for u,alternatives in targets.items():
                counts['root_layout_pairs']+=1
                proposal=probe.bind_layout(req,u,history,domains)
                predicted=tuple((*address(p),p['version']) for p in proposal.boundary) if proposal else None
                counts['pairs_with_observed_boundary']+=predicted in alternatives
                observed[u]=set().union(*alternatives.values())
                reproduced[u]=alternatives.get(predicted,set())
                for boundary,residual in alternatives.items():
                    proven['given_layout_and_boundary'].update(residual)
                    if selected==u:
                        proven['learned_layout_given_boundary'].update(residual)
                    if predicted==boundary:
                        proven['given_layout_learned_boundary'].update(residual)
                        if selected==u:
                            proven['learned_layout_and_boundary'].update(residual)
            context_groups[(tuple(eligible),len(fields))].append(
                (req,context,selected,observed,reproduced))
    with TemporaryDirectory() as tmp:
        path=Path(tmp)/'base.json'
        path.write_text(json.dumps(live.receiver_layouts(),separators=(',',':')))
        run=execute(binary,folder/'program.json',actor,seed,assist=True,graph_issuer=live,
                    layout_file=path,prefix_policy=Policy(32),observe_snapshot=snapshot,
                    frame_observer=lambda frame:receipts.extend(frame['accepted']))
    if receipts!=refs or run['state_sha']!=read(trace/'opportunity.json')['native']['state_sha']:
        raise ValueError('the fixed intervention history differs from the archived trace')
    shuffled=Counter()
    joint=set()
    layouts_only=set()
    for (eligible,_),rows in context_groups.items():
        for j,(req,actual,choice,observed,reproduced) in enumerate(rows):
            other=rows[(j+1)%len(rows)][1]
            changed=not torch.equal(actual,other)
            shuffled['roots_with_changed_input']+=changed
            alternative=probe.choose_layout(req,list(eligible),other)
            shuffled['changed_selections']+=alternative!=choice
            layouts_only.update(observed.get(alternative,()))
            joint.update(reproduced.get(alternative,()))
    shuffled['residuals_given_boundary']=len(layouts_only)
    shuffled['residuals_learned_boundary']=len(joint)
    return dict(context_permutation=shuffled,mode='offline intervention on original assist snapshots',roots=counts,
                distinct_residual={k:len(proven[k]) for k in ('given_layout_and_boundary',
                    'learned_layout_given_boundary','given_layout_learned_boundary','learned_layout_and_boundary')},
                checked_commits=len(receipts),state_sha=run['state_sha'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','base','experiment','old','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--policy',type=Path,help='layout selector for the offline intervention')
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    donors=read(a.donor/'program.json')
    seeds={r['directory']:r['seed'] for r in read(a.root/'manifest.json')}
    result={}
    for name in a.cases:
        result[name]=audit(a.root/name,a.experiment/name,donors,a.binary,a.weights,a.base,
                           a.experiment/'expanded',a.old,a.policy or a.experiment/'refit',1703+seeds.get(name,0))
        a.out.write_text(json.dumps(result,indent=2)+'\n')
