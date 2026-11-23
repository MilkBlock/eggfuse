"""Locate first misses on complete teacher certificates under a frozen, search-free decoder."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch

from alternate_proofs import digest
from anchor_set import Domains
from history import stream
from rule_read import load_actor


@torch.no_grad()
def trace(folder, model, runs, seed):
    reports = {}
    for cat,snap in stream(folder,seed,runs,model.catalog_type):
        mem = model.memory(cat,snap)
        dom = Domains(mem)
        idx = {p.address:i for i,p in enumerate(mem.ports)}
        groups = defaultdict(list)
        misses = Counter()
        for rid,refs in snap.targets:
            if not refs:
                score = model.root_scores(cat,mem,rid,None,None,dom).item()
                misses['empty_rule_pass' if score >= model.thresholds[0] else 'empty_rule_blocked'] += 1
                continue
            js = tuple(idx[a] for a in refs)
            anchor = next(i for i,j in enumerate(js) if not cat.seminaive[rid] or mem.ports[j].version >= mem.rules[rid])
            groups[rid,anchor].append(js)
        roots = []
        for (rid,anchor), paths in groups.items():
            ids = dom.role(cat,mem,rid,anchor,anchor)
            scores = model.root_scores(cat,mem,rid,anchor,ids,dom)
            ports = set(path[anchor] for path in paths)
            positive = torch.tensor([i in ports for i in ids.tolist()])
            passed = scores >= model.thresholds[1]
            # One read sees all roots of the row's typed delta, including alternate
            # proofs. These ranks concern the canonical teacher addresses only.
            roots.append(dict(rule=rid,anchor=anchor,commits=len(paths),domain=len(ids),
                positive=len(ports),selected=int(passed.sum()),positive_selected=int((passed & positive).sum()),
                positive_logit_range=[float(scores[positive].min()),float(scores[positive].max())],
                negative_logit_range=[float(scores[~positive].min()),float(scores[~positive].max())] if (~positive).any() else None))
            lookup = dict(zip(ids.tolist(),scores.tolist()))
            order = [anchor]+[i for i in range(len(paths[0])) if i!=anchor]
            for path in paths:
                if lookup[path[anchor]] < model.thresholds[1]:
                    misses['anchor_blocked'] += 1
                    continue
                for depth,role in enumerate(order[1:],1):
                    prefix = torch.tensor([[path[i] for i in order[:depth]]])
                    score = model.pair_scores(cat,mem,rid,order[:depth],prefix,role,torch.tensor([path[role]])).item()
                    if score < model.thresholds[2]:
                        misses['parent_blocked_depth_'+str(depth+1)] += 1
                        break
                else:
                    misses['canonical_complete'] += 1
        if sum(misses.values()) != len(snap.targets):
            raise ValueError('incomplete teacher packet audit')
        reports[snap.run] = dict(required=len(snap.targets),first_decision=misses,roots=roots)
    return reports


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('root','weights','out'): p.add_argument(k,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--runs',nargs='+',required=True,type=int)
    args = p.parse_args()
    torch.set_num_threads(1)
    meta = json.loads((args.root/'manifest.json').read_bytes())
    seed = {r['directory']:r['seed'] for r in meta}.get(args.case,0)
    model = load_actor(args.weights,True)
    out = dict(case=args.case, weights_sha256=digest(args.weights),cuts=model.thresholds.tolist(),
               runs=trace(args.root/args.case,model,set(args.runs),1703+seed))
    args.out.write_text(json.dumps(out,indent=2)+'\n')
