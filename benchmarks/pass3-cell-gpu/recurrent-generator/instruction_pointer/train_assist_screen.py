"""Imitate productive rules from completed native assist trajectories on training programs."""
import argparse
from collections import Counter
import json
from pathlib import Path

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from entry_coverage import split_runs
from online import execute
from prefix_policy import Policy
from rule_read import load_actor
from rule_screen import RuleContext, RuleScreen


@torch.no_grad()
def collect(folder, binary, actor, seed, horizon):
    history = RuleContext()
    pending = {}
    rows = []
    def frame(raw):
        history.observe(raw)
        earlier = raw['run']-1
        if earlier in pending:
            rids,features = pending.pop(earlier)
            commits = Counter(p['rule'] for p in raw['accepted'])
            if commits.keys() - set(rids):
                raise ValueError('receipt outside scheduled rules')
            rows.append((earlier, features, torch.tensor([commits[r] for r in rids])))
    nodes = None
    def snapshot(catalog,h,s):
        nonlocal nodes
        if nodes is None:
            nodes = actor.template_graph(catalog)
        pending[s.run] = (list(s.rules),history.features(catalog,s,nodes))
    x = execute(binary,folder/'program.json',actor,seed,assist=True,prefix_policy=Policy(32),
                frame_observer=frame,observe_snapshot=snapshot,run_limit=horizon+1)
    ref = json.loads((folder/'capture.json').read_bytes())
    for k,target in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes')]:
        if x[k] != ref[target][:x['runs']]:
            raise ValueError('training assist trajectory diverged')
    if any(int(labels.sum())!=ref['schedule'][r-1][4] for r,_,labels in rows):
        raise ValueError('receipt count differs from source commits')
    return rows


def fit(root,binary,weight,out,horizon):
    torch.set_num_threads(1)
    torch.manual_seed(1703)
    actor = load_actor(weight,True)
    selected, _, reserved = split_runs(root,1703)
    train, calibration = [], []
    exposure = {}
    for rec,_ in selected:
        if rec['origin'] != 'eggcc' or rec['split'] != 'train':
            continue
        n = rec['directory']
        rows = collect(root/n,binary,actor,1703+rec['seed'],horizon)
        exposure[n] = {}
        for r,x,y in rows:
            # Retain a deterministic interleaved subset for cutoff selection, including
            # all original reserved Runs reached by this collector.
            hold = r % 5 == 0 or (n,r) in reserved
            group = calibration if hold else train
            group.append((x,y))
            exposure[n][r] = dict(split='calibration' if hold else 'fit', rules=len(y), commits=int(y.sum()))
    def tensors(group):
        x,y=zip(*group)
        return torch.cat(x).to('mps'),torch.cat(y).to('mps')
    x,y=tensors(train)
    cx,cy=tensors(calibration)
    if not (y>0).any() or not (cy>0).any():
        raise ValueError('no positive training or validation decisions')
    model=RuleScreen().to('mps')
    opt=torch.optim.AdamW(model.parameters(),lr=.003)
    for _ in range(192):
        scores=model(x)
        positive=y>0
        loss=F.softplus(-scores[positive]).mean()+F.softplus(scores[~positive]).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
    with torch.no_grad():
        scores=model(cx)
        # Fix the recall constraint before evaluation. Equal scores enter together.
        positive=scores[cy>0].sort().values
        cut=positive[len(positive)//100]
        model.threshold.copy_(cut)
        keep=scores>=cut
    out.mkdir(parents=True,exist_ok=True)
    torch.save(model.cpu().state_dict(),out/'screen.pt')
    summary=dict(actor=digest(weight),binary=digest(binary),weights=digest(out/'screen.pt'),mode='assist training',
                 horizon=horizon,training_reads=len(x),training_productive=int((y>0).sum()),calibration_reads=len(cx),
                 calibration_productive=len(positive),calibration_selected=int(keep.sum()),
                 calibration_productive_kept=int((keep & (cy>0)).sum()),cut=float(cut),device='mps',exposure=exposure)
    (out/'screen.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','binary','weight','out'):p.add_argument(k,type=Path)
    p.add_argument('--horizon',type=int,default=128)
    a=p.parse_args()
    fit(a.root,a.binary,a.weight,a.out,a.horizon)
