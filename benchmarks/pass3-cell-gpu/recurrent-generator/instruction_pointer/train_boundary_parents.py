"""Fit existing pointer heads on the policy's first private, source-aligned gaps."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check
from entry_coverage import split_runs
from first_boundary import receipt_probe
from online import execute
from prefix_policy import Policy
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


@torch.no_grad()
def collect(folder, binary, actor, seed, horizon, reserved):
    ref = read(folder / 'capture.json')
    tape = read(folder / 'tape.json')
    issued = defaultdict(list)

    def record(packets):
        for packet in packets:
            issued[packet['run']].append(packet)

    def rollout(**kwargs):
        return execute(binary, folder / 'program.json', actor, seed, prefix_policy=Policy(32), **kwargs)

    actual = rollout(run_limit=horizon, observe_packets=record)
    run = next((i + 1 for i in range(actual['runs']) if any(
        actual[key][i] != ref[target][i] for key, target in
        [('source_schedule', 'schedule'), ('rhs_by_run', 'rhs'), ('writes_by_run', 'writes')])), None)
    if run is None or run in reserved:
        return [], dict(first_gap=run, skipped='no eligible gap')
    known = {}
    for r in range(1, run):
        if not issued[r] and not ref['schedule'][r-1][4]:
            continue
        hits, ledger = receipt_probe(folder, binary, tape, issued[r], known, r)
        if ledger['unresolved'] or ledger['distinct'] != ref['schedule'][r-1][4]:
            raise ValueError('incomplete earlier native correspondence')
        known.update(hits)

    requests, groups = [], []
    required = {p['token'] for p in tape['requests'] if p['run'] == run}
    selected = []
    def snapshot(cat, h, snap):
        if snap.run != run:
            return
        mem = actor.memory(cat, snap)
        dom = Domains(mem)
        def premise(j):
            port = snap.ports[j]
            alias, pc = port.address
            token = h.inverse[alias]
            src = token if token < 0 and token % 2 else known.get(token)
            if src is None:
                raise ValueError('unmapped private premise; cannot label as a rejection')
            return dict(address=dict(token=src, op=pc), version=port.version)
        for rid in mem.rules:
            atoms = cat.atoms[rid]
            if len(atoms) not in (1, 2):
                continue
            for anchor in range(len(atoms) if cat.seminaive[rid] else 1):
                roots = dom.role(cat, mem, rid, anchor, anchor)
                if not len(roots):
                    continue
                root_context = torch.cat((mem.nodes[cat.roots['generated', rid]], mem.nodes[atoms[anchor][1]]))
                root_scores = actor.root_scores(cat, mem, rid, anchor, roots, dom) - actor.thresholds[1]
                root_fixed = root_scores - actor.anchor_bias(root_context)
                for j, index in enumerate(roots.tolist()):
                    start = len(requests)
                    if len(atoms) == 1:
                        tuples = [[premise(index)]]
                        terminal = None
                    else:
                        other = 1 - anchor
                        ids = dom.role(cat, mem, rid, anchor, other)
                        if not len(ids):
                            continue
                        prefix = torch.tensor([[index]])
                        ctx = actor.final_context(cat, mem, rid, prefix, other)
                        logits = actor.pair_scores(cat, mem, rid, [anchor], prefix, other, ids)
                        keys = mem.keys[ids]
                        fixed = logits - actor.thresholds[2] - actor.final_adjustment(ctx, keys)
                        terminal = (ctx, keys, fixed.flatten())
                        root_premise = premise(index)
                        tuples = []
                        for k in ids.tolist():
                            other_premise = premise(k)
                            tuples.append([root_premise, other_premise] if anchor == 0
                                          else [other_premise, root_premise])
                    for parents in tuples:
                        requests.append(dict(run=run, rule=rid, token=len(requests)+1, parents=parents))
                    groups.append((root_context, root_fixed[j], terminal, start, len(requests)))
    rollout(run_limit=run, observe_snapshot=snapshot, observe_packets=selected.extend)
    if [p for p in selected if p['run'] == run] != issued[run]:
        raise ValueError('collection changed private proposals')
    verdicts = sorted(check(folder, binary, tape, requests)['recall_verdicts'], key=lambda r:r[1])
    labels = []
    for i, (r, token, w, reason) in enumerate(verdicts, 1):
        if r != run or token != i or (w is not None and w not in required):
            raise ValueError('incorrect native label identity')
        labels.append(w if w is not None else -2 if reason == 'off_reference' else -1)
    seen, _ = receipt_probe(folder, binary, tape, issued[run], known, run)
    rows = [(h, z, term, labels[start:end]) for h, z, term, start, end in groups]
    covered = {w for w in labels if w >= 0}
    return rows, dict(first_gap=run, required=len(required), actual=len(set(seen.values())),
                      labeled_distinct=len(covered), newly_reachable=len(covered-set(seen.values())),
                      native_requests=len(requests), anchors=len(rows), verdicts=Counter(
                          reason for _, _, _, reason in verdicts))


def fit(root, binary, initial, out, horizon, seed):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    actor = load_actor(initial, True)
    selected, _, reserved = split_runs(root, seed)
    data, stats = [], {}
    for rec, _ in selected:
        if rec['origin'] == 'eggcc' and rec['split'] == 'train':
            name = rec['directory']
            rows, stats[name] = collect(root/name, binary, actor, seed+rec['seed'], horizon,
                                        {r for n,r in reserved if n == name})
            data.extend(rows)
            print(name, stats[name], flush=True)
    if not data:
        raise ValueError('training had no private source-aligned gaps')
    # Each named alternative belongs to a native commit, even across different roots.
    # Compute the probability of one complete request from both pointer logits.
    pools = []
    start = 0
    for stats_row in stats.values():
        count = stats_row.get('anchors', 0)
        if not count:
            continue
        rows = data[start:start+count]
        start += count
        roots = torch.stack([row[0] for row in rows]).to('mps')
        offsets = torch.stack([row[1] for row in rows]).to('mps')
        terms = [(i, *[t.to('mps') for t in row[2]]) for i,row in enumerate(rows) if row[2] is not None]
        owners, winners, bad = [], defaultdict(list), []
        for i, row in enumerate(rows):
            for label in row[3]:
                pos = len(owners)
                owners.append(i)
                if label >= 0:
                    winners[label].append(pos)
                elif label == -1:
                    bad.append(pos)
        if not winners:
            continue
        ranges = []
        end = 0
        for _, _, _, labels in rows:
            ranges.append(end)
            end += len(labels)
        pools.append((roots, offsets, terms, ranges, torch.tensor(owners, device='mps'),
                      [torch.tensor(g, device='mps') for g in winners.values()],
                      torch.tensor(bad, dtype=torch.long, device='mps')))
    if not pools:
        raise ValueError('no reachable training winners')
    actor.to('mps')
    heads = [*actor.anchor_bias.parameters(), *actor.final_query.parameters()]
    opt = torch.optim.AdamW(heads, lr=0.001)
    initial_heads = [p.detach().clone() for p in heads]
    for _ in range(64):
        losses = []
        for roots, offsets, terms, ranges, owners, good, bad in pools:
            root = (offsets + actor.anchor_bias(roots).flatten())[owners]
            # Unary requests need only their anchor. For binary requests both gates must pass.
            joint = root.clone()
            for i, ctx, keys, fixed in terms:
                pos = ranges[i]
                terminal = fixed + actor.final_adjustment(ctx, keys).flatten()
                joint[pos:pos+len(keys)] = torch.minimum(root[pos:pos+len(keys)], terminal)
            best = torch.stack([joint[g].max() for g in good])
            loss = F.softplus(-best).mean()
            if len(bad):
                loss = loss + F.softplus(joint[bad].topk(min(len(bad), len(good))).values).mean()
            loss = loss + 0.1 * torch.stack([joint[g].sigmoid().sum() for g in good]).sub(best.sigmoid()).mean()
            losses.append(loss)
        value = torch.stack(losses).mean() + sum((p-q).square().sum() for p,q in zip(heads,initial_heads)) * 0.05
        if not value.isfinite():
            raise ValueError('non-finite loss')
        opt.zero_grad(set_to_none=True)
        value.backward()
        opt.step()
    actor.cpu()
    state = torch.load(initial, map_location='cpu', weights_only=True)
    changed = [k for k,v in actor.state_dict().items() if not torch.equal(state['parameters'][k], v)]
    if not changed or any(not k.startswith(('anchor_bias.', 'final_query.')) for k in changed):
        raise ValueError('unexpected trainable parameter changes')
    state['parameters'] = actor.state_dict()
    out.mkdir(parents=True, exist_ok=True)
    torch.save(state, out/'model.pt')
    (out/'training.json').write_text(json.dumps(dict(device='mps',steps=64,horizon=horizon,training=stats,
        receiver=digest(binary),initial=digest(initial),weights=digest(out/'model.pt'),changed=changed),indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root','binary','initial','out'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--horizon', type=int, default=20)
    args = parser.parse_args()
    fit(args.root, args.binary, args.initial, args.out, args.horizon, 1703)
