"""Choose two scalar root biases from complete named requests on reserved training Runs."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import product
import json
from pathlib import Path

import torch

from alternate_proofs import digest
from anchor_set import CalibratedAnchorActor
from anchor_set_audit import check
from entry_coverage import split_runs
from history import History
from prefix_policy import Policy, generate
from rule_read import load_actor


@torch.no_grad()
def calibrate(root, binary, initial, out, seed):
    torch.set_num_threads(1)
    base = load_actor(initial, True)
    if isinstance(base,CalibratedAnchorActor):
        model=deepcopy(base)
        export_format=torch.load(initial,weights_only=True,map_location='cpu')['format']
    else:
        model=CalibratedAnchorActor(base.vocabulary,base.name_mode).eval()
        missing,extra=model.load_state_dict(base.state_dict(),strict=False)
        if missing!=['root_offset'] or extra:
            raise ValueError('a frozen field-disagreement policy is required')
        export_format='calibrated-anchor-v1'
    starting=model.root_offset.tolist()
    offsets=sorted(set([0.,1.,2.,3.,4.,6.,8.]+starting))
    ledger = {b: defaultdict(Counter) for b in offsets}
    selected, _, reserved = split_runs(root, seed)
    required = Counter()
    used = {}
    for record, _ in selected:
        name = record['directory']
        runs = {r for n,r in reserved if n == name}
        if not runs:
            continue
        if record['split'] != 'train':
            raise ValueError('unexpected calibration source')
        used[name] = sorted(runs)
        folder = root/name
        tape = json.loads((folder/'tape.json').read_bytes())
        cat = model.catalog_type(json.loads((folder/'program.json').read_bytes()))
        for packet in tape['requests']:
            if packet['run'] in runs:
                required[min(2,len(packet['parents']))] += 1
        nodes = model.template_graph(cat)
        hist = History(cat, seed+record['seed'])
        packets = []
        memberships = defaultdict(list)
        with (folder/'memory.jsonl').open() as lines:
            for line in lines:
                raw = json.loads(line)
                snap = hist.snapshot(raw, raw['run'] in runs)
                if snap is None:
                    continue
                mem = model.memory(cat, snap, nodes)
                # Probe each distinct full certificate once; both kinds can be
                # swept together since the frontier budget is local to a rule.
                for bias in offsets:
                    model.root_offset.fill_(bias)
                    for rid, refs in generate(model,cat,mem,Policy(32)):
                        key = snap.run, rid, refs
                        if key not in memberships:
                            parents = []
                            for alias,pc in refs:
                                tok = hist.inverse[alias]
                                parents.append(dict(address=dict(token=tok,op=pc),version=hist.visible[tok,pc]['version']))
                            packets.append(dict(run=snap.run,rule=rid,token=len(packets)+1,parents=parents))
                        memberships[key].append(bias)
                if snap.run == max(runs):
                    break
        audits = check(folder,binary,tape,packets)['recall_verdicts']
        hits = defaultdict(set)
        for packet, biases, verdict in zip(packets,memberships.values(),sorted(audits,key=lambda v:v[1]),strict=True):
            run,token,winner,why = verdict
            if (run,token)!=(packet['run'],packet['token']) or len(set(biases))!=len(biases):
                raise ValueError('different native request')
            kind = min(2,len(packet['parents']))
            for b in biases:
                c = ledger[b][kind]
                c['issued'] += 1
                if winner is None:
                    c[why] += 1
                elif (run,winner) in hits[b,kind]:
                    c['duplicates'] += 1
                else:
                    hits[b,kind].add((run,winner))
                    c['recovered'] += 1
    # F2 emphasizes recall, charging every issued proof including rejected and
    # repeated ones. Ties favor fewer packets and then smaller score corrections.
    grid = []
    for unary,multi in product(offsets,repeat=2):
        c = ledger[0.][0]+ledger[unary][1]+ledger[multi][2]
        f2 = 5*c['recovered']/(4*sum(required.values())+c['issued'])
        grid.append(dict(offsets=[unary,multi],f2=f2,counts=dict(c)))
    def order(row):
        return row['f2'], -row['counts']['issued'], -sum(row['offsets'])
    best = max(grid,key=order)
    shared = max((g for g in grid if g['offsets'][0]==g['offsets'][1]),key=order)
    model.root_offset.copy_(torch.tensor(best['offsets']))
    if any(not torch.equal(v,model.state_dict()[n]) for n,v in base.state_dict().items() if n!='root_offset'):
        raise ValueError('frozen parameters changed')
    out.mkdir(parents=True,exist_ok=True)
    torch.save(dict(format=export_format,names=model.name_mode,vocabulary=list(model.vocabulary),
                    parameters=model.state_dict()),out/'model.pt')
    report = dict(seed=seed,initial_sha256=digest(initial),weights_sha256=digest(out/'model.pt'),
                  receiver_sha256=digest(binary),runs=used,required=required,calibration=ledger,
                  grid=grid,baseline=next(row for row in grid if row['offsets']==starting),shared=shared,selected=best,top_k=32)
    (out/'training.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['baseline'],shared,best,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','receiver','initial','out'):p.add_argument(name,type=Path)
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args()
    calibrate(a.root,a.receiver,a.initial,a.out,a.seed)
