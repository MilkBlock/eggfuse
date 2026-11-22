"""Replay signed ports. Source labels are consulted only after model issuance."""
import argparse
from collections import Counter
from itertools import groupby
import json
from pathlib import Path

import numpy as np
import torch

from batched_parent_read import BucketEncoder, encode, histories, train_encoder
from history_reader import fit_cutoff


def fit_block(steps, width=64):
    torch.manual_seed(27)
    model = BucketEncoder(width)
    opt = torch.optim.Adam(model.parameters(), lr=.02)
    rng = torch.Generator().manual_seed(87413)
    for _ in range(steps):
        left, right = histories(rng, 64, 32, 128)
        names = torch.randint(1 << 30, (128,), generator=rng)
        lhs, rhs = model(names[left]), model(names[right])
        # Any true member is dominated coordinatewise for every possible set
        # of weights. Train only the separating margin for absent members.
        absent = ~(names[left][:, :, None] == names[right][:, None, :]).any(-1)
        gap = (lhs - rhs.amax(1, keepdim=True)).amax(-1)
        loss = (.45 - gap[absent]).clamp_min(0).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return model


def waves(events):
    banks = [{}, {}]
    for epoch, batch in groupby(events, key=lambda r: r[0]):
        fresh = [{}, {}]
        for _, owner, slot, role, cell, op, version, key in batch:
            addr = cell, op, version
            old = fresh[role].get(addr, banks[role].get(addr))
            if old is None or key != old[0]:
                fresh[role][addr] = key, owner, slot
        for role in (0, 1):
            if fresh[role] and banks[1-role]:
                yield epoch, role, sorted(fresh[role].items()), sorted(banks[1-role].items())
            banks[role].update(fresh[role])


def issue(events, mode, model, cutoff):
    # Fixed trained bit-distance head with distance cutoff zero admits exactly
    # equal subjects. A comparison never supplies an unobserved address.
    assert cutoff['max_distance'] == 0
    seen, counters = {}, Counter()
    feature_cache = {}

    def features(items):
        keys = [v[0] for _, v in items]
        missing = sorted(set(keys).difference(feature_cache))
        if missing:
            # Reduce Python unsigned keys before signed tensor multiplication.
            ids = torch.tensor([k % 2147483647 for k in missing])
            features = encode(model, ids) if mode.startswith('pooled12') else model(ids)
            feature_cache.update(zip(missing, features.detach().numpy()))
        return np.stack([feature_cache[k] for k in keys])

    for epoch, role, fresh, bank in waves(events):
        keys = np.array([v[0] for _, v in bank], dtype=np.uint64)
        query = np.array([v[0] for _, v in fresh], dtype=np.uint64)
        if mode != 'all':
            lhs, rhs = features(fresh), features(bank)
        if mode.startswith('pooled12'):
            values = (lhs * rhs.sum(0)).reshape(len(lhs), 4, -1).sum(-1).min(-1)
            if mode == 'pooled12':
                selected = np.argsort(-values, kind='stable')[:12]
            else:
                selected = np.concatenate([offset + np.argsort(-values[offset:offset+32], kind='stable')[:12]
                                           for offset in range(0, len(values), 32)])
        else:
            selected = np.arange(len(fresh))
        for start in range(0, len(keys), 32):
            group = selected
            if mode.startswith('block'):
                limit = rhs[start:start + 32].max(0)
                group = np.flatnonzero((lhs <= limit).all(1))
                counters['parent_block_scores'] += len(fresh)
            part = keys[start:start + 32]
            counters['pair_scores'] += len(group) * len(part)
            i, j = np.nonzero(query[group, None] == part)
            for l, r in zip(group[i], start+j):
                a, av = fresh[l]
                b, bv = bank[r]
                pair = (a, b) if role == 0 else (b, a)
                owners = (av[1:], bv[1:]) if role == 0 else (bv[1:], av[1:])
                seen.setdefault(pair, (epoch, owners))
    return seen, counters


def evaluate(path, native, models, cutoff):
    data = json.loads(path.read_text())
    report = {}
    baseline = None
    for mode, model in models.items():
        with torch.no_grad():
            issued, counts = issue(data['events'], mode, model, cutoff)
        hits = set()
        for epoch, refs in data['labels']:
            pair = tuple(map(tuple, refs))
            if pair in issued and issued[pair][0] < epoch:
                hits.add(pair)
        if mode == 'all':
            baseline = issued
            native_packets = {tuple(map(tuple, refs)): birth for refs, birth in data['native_births']}
            if {pair: row[0] for pair, row in issued.items()} != native_packets:
                raise ValueError('named pair or birth epoch differs from native issuance')
            if (len(issued), len(hits), counts['pair_scores']) != (native['proposed'], native['matched_once'], native['scores']):
                raise ValueError("replay differs from native-checked reader")
        identical = issued == baseline
        if mode.startswith('block') and not identical:
            raise ValueError("block reader changed a signed reference, owner or issue epoch")
        report[mode] = dict(source=len(data['labels']), matched=len(hits), proposed=len(issued),
                            extra=len(issued)-len(hits), same_receipts_as_all=identical, **counts)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('history', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    native = json.loads((args.history / 'catalog-credit.json').read_text())['cases']
    models = dict(all=None, pooled12=train_encoder('cpu', 256, 200, 27, True),
                  block_random=fit_block(0), block_trained=fit_block(200),
                  block_narrow=fit_block(200, 16), block_wide=fit_block(200, 256))
    models['pooled12_per32'] = models['pooled12']
    cutoff = fit_cutoff(True)
    results = {}
    for case, record in native.items():
        reference = record['sub_expected_guard']['history_reader']['with_citations']
        results[case] = evaluate(args.history / (case + '-reader-history.json'), reference, models, cutoff)
    args.output.write_text(json.dumps(results, indent=2) + '\n')
