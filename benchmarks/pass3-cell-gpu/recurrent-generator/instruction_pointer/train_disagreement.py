"""Fit one frozen-pointer correction from native verdicts on named training requests."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from alternate_proofs import addr, digest
from anchor_set import DisagreementActor, Domains
from anchor_set_audit import check
from entry_coverage import split_runs
from history import History
from rule_read import load_actor


@torch.no_grad()
def collect(folder, binary, model, runs, seed):
    rng = random.Random(seed)
    cat = model.catalog_type(json.loads((folder / 'program.json').read_bytes()))
    tape = json.loads((folder / 'tape.json').read_bytes())
    teacher = defaultdict(list)
    for request in tape['requests']:
        if request['run'] in runs and len(request['parents']) >= 2:
            teacher[request['run']].append(request)
    if not teacher:
        return [], Counter()
    history = History(cat, seed)
    nodes = model.template_graph(cat)
    measurements = {}
    packets = []
    with (folder / 'memory.jsonl').open() as stream:
        for line in stream:
            frame = json.loads(line)
            run = frame['run']
            snap = history.snapshot(frame, run in teacher)
            if snap is None:
                continue
            mem = model.memory(cat, snap, nodes)
            dom = Domains(mem)
            indices = {port.address: j for j, port in enumerate(snap.ports)}
            for req in rng.sample(teacher[run], min(12, len(teacher[run]))):
                rid, parents = req['rule'], req['parents']
                original = [indices[history.rename(addr(ref['address']))] for ref in parents]
                anchor = next(i for i, ref in enumerate(parents)
                              if not cat.seminaive[rid] or ref['version'] >= snap.rules[rid])
                order = [anchor] + [j for j in range(len(parents)) if j != anchor]
                for depth, role in enumerate(order[1:], 1):
                    prior = order[:depth]
                    ids = dom.role(cat, mem, rid, anchor, role)
                    prefix = torch.tensor([[original[j] for j in prior]])
                    scores, distances = model.pair_components(cat, mem, rid, prior, prefix, role, ids, measure=True)
                    domain = ids.tolist()
                    probes = set(scores[0].topk(min(8, len(domain))).indices.tolist())
                    probes.update(rng.sample(range(len(domain)), min(3, len(domain))))
                    probes.add(domain.index(original[role]))
                    for col in sorted(probes):
                        port = mem.ports[domain[col]]
                        alias, pc = port.address
                        refs = parents.copy()
                        refs[role] = dict(address=dict(token=history.inverse[alias], op=pc), version=port.version)
                        key = run, rid, tuple(addr(r['address']) for r in refs)
                        if key not in measurements:
                            packets.append(dict(token=len(packets)+1, run=run, rule=rid, parents=refs))
                            measurements[key] = len(packets), []
                        measurements[key][1].append((float(scores[0,col]-model.thresholds[2]), float(distances[0,col])))
            if run == max(teacher):
                break
    verdicts = check(folder, binary, tape, packets)['recall_verdicts']
    counts = Counter()
    data = []
    by_token = sorted(verdicts, key=lambda v: v[1])
    for (run, token, winner, reason), (expected, reads) in zip(by_token, measurements.values(), strict=True):
        if token != expected or packets[token-1]['run'] != run:
            raise ValueError('native verdict order mismatch')
        counts['accepted' if winner is not None else reason] += 1
        if winner is None and reason == 'off_reference':
            continue
        data.extend((score, distance, int(winner is not None)) for score, distance in reads)
    return data, counts


def train(root, binary, initial, out, seed):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    base = load_actor(initial, True)
    model = DisagreementActor(base.vocabulary, base.name_mode)
    missing, extra = model.load_state_dict(base.state_dict(), strict=False)
    if missing != ['disagreement_scale'] or extra:
        raise ValueError('different base architecture')
    selected, fitted, _ = split_runs(root, seed)
    rows, per_program = [], {}
    for rec, _ in selected:
        name = rec['directory']
        if rec['split'] != 'train':
            raise ValueError('held program in training set')
        runs = {r for n,r in fitted if n == name}
        data, counts = collect(root/name, binary, model, runs, seed+rec['seed'])
        per_program[name] = dict(counts)
        rows.extend(data)
    x = torch.tensor(rows, device='mps')
    pos = (x[:,2] == 1).nonzero().flatten()
    neg = (x[:,2] == 0).nonzero().flatten()
    model.to('mps')
    scale = model.disagreement_scale
    opt = torch.optim.Adam([scale], lr=.045)
    for _ in range(384):
        batch = torch.cat([pool[torch.randint(len(pool), (128,), device='mps')] for pool in (pos, neg)])
        z, d, y = x[batch].T
        loss = F.binary_cross_entropy_with_logits(z-scale*d, y)+.0001*scale.square()
        opt.zero_grad()
        loss.backward()
        opt.step()
        with torch.no_grad():
            scale.clamp_(min=0)
    model.cpu()
    if not 0 < scale.item() or any(not torch.equal(base.state_dict()[n],v) for n,v in model.state_dict().items()
                                   if n != 'disagreement_scale'):
        raise ValueError('missing correction or modified backbone')
    out.mkdir(parents=True, exist_ok=True)
    torch.save(dict(format='parent-disagreement-v1', names=model.name_mode, vocabulary=list(model.vocabulary),
                    parameters=model.state_dict()), out/'model.pt')
    counts = Counter((('accepted' if y else 'rejected')+('_disagrees' if d else '_agrees')) for _,d,y in rows)
    report = dict(device='mps', seed=seed, updates=384, fitted_scale=scale.item(), native=per_program,
                  supervised_reads=counts, frozen_sha256=digest(initial), weights_sha256=digest(out/'model.pt'),
                  receiver_sha256=digest(binary))
    (out/'training.json').write_text(json.dumps(report, indent=2)+'\n')
    print(scale.item(), counts, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root','binary','initial','out'):
        parser.add_argument(key,type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    args = parser.parse_args()
    train(args.root, args.binary, args.initial, args.out, args.seed)
