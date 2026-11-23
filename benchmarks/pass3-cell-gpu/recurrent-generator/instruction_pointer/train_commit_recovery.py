"""Fine-tune the existing root pointer against sets of native commits."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F
from torch.nn.utils.rnn import pad_sequence

from alternate_proofs import digest
from higher_cell import read
from marginal_policy import splits
from prefix_recovery import Recovery


def examples(root, data, weights, protocol):
    parts, groups, covered, controls, sources = [], [], [], [], {}
    offset = 0
    receivers = set()
    for name, fingerprint in protocol['train'].items():
        report = read(data / (name + '.json'))
        file = data / (name + '.pt')
        if (digest(file) != report['data'] or report['program'] != fingerprint or
                digest(root/name/'program.json') != fingerprint or report['base'] != digest(weights) or
                report['tape'] != digest(root/name/'tape.json')):
            raise ValueError('training examples differ from pinned sources')
        receivers.add(report['receiver'])
        sources[name] = report
        rows = torch.load(file, weights_only=True)
        winners = rows['winner']
        observed = winners >= 0
        if (not torch.equal(rows['y'][observed], winners[observed] > 0)
                or int(observed.sum()) != report['native_checked']):
            raise ValueError('complete-proof labels differ from the native audit')
        hits = set(rows['covered'].tolist())
        families = defaultdict(list)
        for i in ((winners > 0) & ~rows['reserved']).nonzero().flatten().tolist():
            families[int(winners[i])].append(i + offset)
        for winner, members in families.items():
            groups.append(torch.tensor(members))
            covered.append(winner in hits)
        controls.append(((winners <= 0) & ~rows['reserved']).nonzero().flatten() + offset)
        parts.append(rows)
        offset += len(winners)
    if len(receivers) != 1 or not groups or all(covered):
        raise ValueError('incompatible native collectors or missing uncovered groups')
    values = [torch.cat([rows[key] for rows in parts]).to('mps') for key in ('ctx','ports','ev')]
    return values, groups, torch.tensor(covered), torch.cat(controls), sources


def set_loss(scores, present, covered, price):
    # One valid certificate is sufficient for an uncovered commit. Further
    # certificates still cost a proposal, including every one for a covered commit.
    log_miss = F.logsigmoid(-scores).masked_fill(~present, 0.).sum(1)
    hit_probability = -torch.expm1(log_miss)
    missed = -hit_probability.clamp_min(1e-8).log()
    cost = scores.sigmoid().masked_fill(~present, 0.).sum(1)
    return (missed.masked_fill(covered, 0.) + price * cost).mean()


def fit(root, data, weights, base, protocol_file, output):
    protocol = splits(protocol_file)
    values, groups, covered, controls, sources = examples(root, data, weights, protocol)
    initial = Recovery(base,weights)
    head = initial.head.to('mps').train()
    torch.manual_seed(protocol['seed'])
    rng = random.Random(protocol['seed'])
    with torch.no_grad():
        prior = head(*values).detach()
    opt = torch.optim.AdamW(head.parameters(), lr=protocol['lr'])
    order = list(range(len(groups)))
    for _ in range(protocol['epochs']):
        rng.shuffle(order)
        for start in range(0,len(order),64):
            ids = order[start:start+64]
            padded = pad_sequence([groups[i] for i in ids],batch_first=True,padding_value=-1).to('mps')
            mask = padded >= 0
            # Padding is discarded by both terms of the set loss.
            index = padded.clamp_min(0)
            logits = head(*(v[index] for v in values)) - initial.cut
            objective = set_loss(logits,mask,covered[ids].to('mps'),protocol['packets_weight'])
            # Preserve the existing partial-read and invalid-proof policy while
            # changing how complete valid certificates share supervision.
            keep = controls[torch.randint(len(controls),(2*len(ids),))].to('mps')
            preserve = F.smooth_l1_loss(head(*(v[keep] for v in values)),prior[keep])
            opt.zero_grad()
            (objective + preserve).backward()
            opt.step()
    output.mkdir(parents=True,exist_ok=True)
    torch.save(head.cpu().state_dict(),output/'head.pt')
    meta = dict(base=digest(weights),head=digest(output/'head.pt'),width=values[1].shape[1],
                budget=initial.budget,cut=initial.cut,margin_cut=read(base/'training.json')['margin_cut'],
                initial=initial.checkpoint,programs=sources,protocol=digest(protocol_file),
                valid_proofs=sum(map(len,groups)),distinct_commits=len(groups),
                base_covered_groups=int(covered.sum()),multiple_proof_groups=sum(len(g)>1 for g in groups),
                held_runs_excluded=True,device='mps')
    (output/'training.json').write_text(json.dumps(meta,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root','data','weights','base','protocol','out'):
        p.add_argument(key,type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    fit(args.root,args.data,args.weights,args.base,args.protocol,args.out)
