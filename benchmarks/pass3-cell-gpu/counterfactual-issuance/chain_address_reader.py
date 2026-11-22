"""Three named parents, two learned field selections and no verifier discovery."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations, groupby
import json
from pathlib import Path

import torch


def routes(layout):
    edges = []
    for a, b in combinations(range(3), 2):
        choices = [(i, j) for i, x in enumerate(layout[a]) for j, y in enumerate(layout[b]) if x == y]
        if choices:
            if len(choices) != 1:
                raise ValueError("expected one common slot per edge")
            edges.append((a, b, *choices[0]))
    if len(edges) != 2:
        raise ValueError("expected a length-two join")
    return edges


def train(layout, varied):
    # The compiler specifies which roles interact. The pointer logits get
    # supervision only from whether a field pair separates a positive example
    # and its one-port counterfactual. There are no real trace labels here.
    rng = torch.Generator().manual_seed(312)
    values = torch.randint(1 << 20, (512, max(map(max, layout))+1), generator=rng)
    if not varied:
        values[:] = values[:, :1].clone()
    learned = []
    for a, b, _, _ in routes(layout):
        lhs, rhs = values[:, layout[a]], values[:, layout[b]]
        correct = ((lhs[:, :, None] == rhs[:, None, :]) &
                   (lhs[:, :, None] != rhs.roll(1, 0)[:, None, :])).flatten(1)
        scores = torch.nn.Parameter(torch.zeros(correct.shape[1]))
        opt = torch.optim.Adam([scores], lr=.08)
        for _ in range(40):
            opt.zero_grad()
            logp = scores.log_softmax(0).expand_as(correct)
            loss = -logp.masked_fill(~correct, -torch.inf).logsumexp(1).mean()
            loss.backward()
            opt.step()
        learned.append((a, b, *divmod(int(scores.argmax()), len(layout[b]))))
    return learned


def replay(data, edges, with_returns=False, latest_only=False):
    adjacent = [[] for _ in range(3)]
    for a, b, i, j in edges:
        adjacent[a].append((b, i, j))
        adjacent[b].append((a, j, i))
    bank = [{}, {}, {}]
    index = defaultdict(set)
    current = [{}, {}, {}]
    issued = {}
    counts = Counter()
    diagnoses = Counter()
    missing_ports = Counter()
    seen_physical = [set(), set(), set()]

    def extend(bound, role):
        for other, col, dest in adjacent[role]:
            if other in bound:
                continue
            key = bank[role][bound[role]][0][col]
            if key is None:
                return
            counts['reads'] += 1
            for addr in index.get((other, dest, key), ()):
                counts['addresses_read'] += 1
                child = dict(bound)
                child[other] = addr
                if len(child) == 3:
                    triple = tuple(child[i] for i in range(3))
                    owners = tuple(bank[i][addr][1] for i, addr in enumerate(triple))
                    issued.setdefault(triple, (epoch, owners))
                else:
                    bridge = other if len(adjacent[other]) == 2 else role
                    extend(child, bridge)
            return

    # Source labels are read at the start of their epoch, solely to diagnose
    # misses. No result of this block enters bank, index, or extend().
    history = data['events']
    if with_returns:
        history = sorted([*history, *data['returns']], key=lambda r: (r[0], r[3], r[4] >= 0, r[4]))
    events = {ep:list(rows) for ep, rows in groupby(history, key=lambda x:x[0])}
    labels = defaultdict(list)
    for ep, refs in data['labels']:
        labels[ep].append(tuple(map(tuple, refs)))
    matched = set()
    for epoch in sorted(events.keys() | labels.keys()):
        for triple in labels.get(epoch, ()):
            if triple in issued:
                matched.add(triple)
            elif any(addr not in bank[i] for i, addr in enumerate(triple)):
                diagnoses['unseen_version'] += 1
                missing = [data['tables'][i] + ('/other_version' if addr[:-1] in seen_physical[i] else '/unseen')
                           for i, addr in enumerate(triple) if addr not in bank[i]]
                missing_ports[' + '.join(missing)] += 1
            else:
                fields = [bank[i][v][0] for i, v in enumerate(triple)]
                pairs = [(fields[a][i], fields[b][j]) for a, b, i, j in edges]
                if any(x is None or y is None for x, y in pairs):
                    diagnoses['missing_field'] += 1
                elif any(x != y for x, y in pairs):
                    diagnoses['observed_keys_disagree'] += 1
                else:
                    raise ValueError('fully observable join lost by incremental reader')
        for _, role, raw, owner, atom, fields in events.get(epoch, ()):
            addr = tuple(raw)
            seen_physical[role].add(addr[:-1])
            if latest_only:
                previous = current[role].get(addr[:-1])
                if previous and previous[-1] > addr[-1]:
                    counts['older_observations'] += 1
                    continue
                if previous and previous != addr:
                    old_values, _ = bank[role].pop(previous)
                    for _, col, _ in adjacent[role]:
                        if old_values[col] is not None:
                            index[role, col, old_values[col]].discard(previous)
                    counts['superseded'] += 1
                current[role][addr[:-1]] = addr
            vals = tuple(json.dumps(v, sort_keys=True) if v is not None else None for v in fields)
            old = bank[role].get(addr)
            if old and old[0] == vals:
                continue
            for _, col, _ in adjacent[role]:
                if old and old[0][col] is not None:
                    index[role, col, old[0][col]].discard(addr)
                if vals[col] is not None:
                    index[role, col, vals[col]].add(addr)
            bank[role][addr] = vals, (owner,atom)
            extend({role:addr}, role)
    if len(matched) + sum(diagnoses.values()) != len(data['labels']):
        raise ValueError('source occurrences are not distinct three-port witnesses')
    return dict(source=data['source'], fully_named=len(data['labels']), matched=len(matched),
                proposed=len(issued), extra=len(issued)-len(matched), misses=dict(diagnoses), missing_ports=dict(missing_ports), **counts)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('history', type=Path)
    p.add_argument('out', type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    result = {}
    for path in sorted(args.history.glob('*-chain-history.json')):
        case = path.name.removesuffix('-chain-history.json')
        rows = {}
        for rule, data in json.loads(path.read_text()).items():
            learned = train(data['layout'], True)
            compiler = routes(data['layout'])
            if compiler != learned:
                raise ValueError('generated counterfactuals did not identify compiler wiring')
            rows[rule] = dict(tables=data['tables'], learned=learned, compiler=compiler,
                              aliased=train(data['layout'], False), citations=replay(data, learned),
                              with_returns=replay(data, learned, True),
                              latest=replay(data, learned, True, True))
        result[case] = rows
    if set(result) != {'dot-product','sum-bits','3mm'}:
        raise ValueError('incomplete workload export')
    args.out.write_text(json.dumps(result, indent=2)+'\n')
