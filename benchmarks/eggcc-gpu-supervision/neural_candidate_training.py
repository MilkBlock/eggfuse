"""Synthetic pooled interfaces for learned matching; never samples real Runs.

Canonical constructor closure is applied before forming Cartesian candidates.
Candidates include independently generated neighbours, repeated variables and
incidental sharing. Bounded sampling is not exhaustive interaction coverage.
"""
import itertools
import numpy as np
import mlx.core as mx
from device_snapshot_import import identity
from neural_snapshot_candidates import import_interfaces, binding_key, relational_edges
from reference_union_family import Reference
from multi_entry_ridge import template


def synthetic_snapshot(recipe, seed, examples=16, shared_fraction=.35):
    if examples < 1 or not 0 <= shared_fraction <= 1:
        raise ValueError("positive examples and bounded sharing probability required")
    rng = np.random.default_rng(seed)
    rows, ids, shared = [], {}, {}
    for ri, rule in enumerate(recipe['rules']):
        for example in range(examples):
            values = {}
            for atom in rule['query']:
                for arg in atom['args']:
                    slot = arg['slot']
                    if slot in values:
                        continue
                    sort = rule['slots'][slot]['sort']
                    if sort['kind'] == 'eq':
                        same = [v for v in values.values() if v['sort'] == sort['name'] and 'eq' in v]
                        pool = shared.get(sort['name'], [])
                        if same and rng.random() < .3:
                            value = dict(same[int(rng.integers(len(same)))])
                        elif shared_fraction > 0 and pool and rng.random() < shared_fraction:
                            value = dict(pool[int(rng.integers(len(pool)))])
                        else:
                            value = dict(sort=sort['name'], eq=f'{ri}:{example}:{slot}')
                            shared.setdefault(sort['name'], []).append(value)
                    elif sort['kind'] == 'i64':
                        value = dict(sort=sort['name'], value=int(rng.integers(-4, 9)))
                    elif sort['kind'] == 'String':
                        value = dict(sort=sort['name'], value='s'+str(rng.integers(0, 12)))
                    else:
                        raise ValueError('unsupported synthetic scalar')
                    values[slot] = value
                    ids.setdefault(identity(value), len(ids))
            for atom in rule['query']:
                rows.append(dict(table=atom['call']['table'], values=[values[arg['slot']] for arg in atom['args']], subsumed=False))
    ref = Reference(recipe, [], ids)
    for row in rows:
        fields = [ids[identity(v)] for v in row['values']]
        ref.construct(row['table'], fields[:-1], fields[-1])
    ref.close()
    normalized = []
    for row in rows:
        fields = [dict(v, eq=str(ref.root(ids[identity(v)]))) if 'eq' in v else dict(v) for v in row['values']]
        normalized.append(dict(row, values=fields))
    return dict(rows=normalized)


def pooled_candidates(recipe, seed, examples=16, per_class=128, scan_limit=200000, shared_fraction=.35):
    if per_class < 1 or scan_limit < 1:
        raise ValueError("positive sample capacities required")
    snapshot = synthetic_snapshot(recipe, seed, examples, shared_fraction)
    rows, ids, pools, x, labels, roles = import_interfaces(recipe, snapshot)
    # A second independent initialization rejects noncanonical generated inputs.
    Reference(recipe, rows, ids)
    rng = np.random.default_rng(seed + 1)
    atoms = max(len(r['query']) for r in recipe['rules'])
    chosen, masks, requests, valid, rids, coverage = [], [], [], [], [], []
    for rid, rule in enumerate(recipe['rules']):
        rp = [pools[a['call']['table']] for a in rule['query']]
        # Reservoir sampling does not bias training toward the first interfaces.
        buckets, counts = [[], []], [0, 0]
        scanned = 0
        for sources in itertools.islice(itertools.product(*rp), scan_limit):
            label = int(binding_key(rule, sources, rows, ids) is not None)
            counts[label] += 1; scanned += 1
            bucket = buckets[label]
            if len(bucket) < per_class:
                bucket.append(sources)
            else:
                j = int(rng.integers(counts[label]))
                if j < per_class:
                    bucket[j] = sources
        _, request = template(rule)
        for label, bucket in enumerate(buckets):
            for sources in bucket:
                chosen.append(list(sources) + [0]*(atoms-len(sources)))
                masks.append([True]*len(sources) + [False]*(atoms-len(sources)))
                requests.append(request); valid.append(label); rids.append(rid)
        coverage.append(dict(rule=rid, candidates=int(np.prod([len(p) for p in rp])), scanned=scanned,
                             positive_seen=counts[1], negative_seen=counts[0], positive_kept=len(buckets[1]), negative_kept=len(buckets[0])))
    indices = np.array(chosen, np.int32)
    # Chunk feature packing so candidate growth does not create an all-pairs tensor.
    edge = []
    dl, dr = mx.array(labels), mx.array(roles)
    for start in range(0, len(indices), 256):
        e = relational_edges(dl, dr, mx.array(indices[start:start+256])); mx.eval(e)
        edge.append(np.array(e))
    return dict(x=x[indices], edges=np.concatenate(edge), mask=np.array(masks),
                request=np.array(requests), valid=np.array(valid, np.float32), rule=np.array(rids, np.int32)), coverage
