"""GPU candidate tuples from seed Cell interfaces, without CPU successful matches.

Standalone snapshot audit, not saturation or ownership execution. Static table
pools are imported once. The Cartesian diagnostic is deliberately complete;
chunking bounds memory but does not remove combinatorial candidate work.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import mlx.core as mx
import numpy as np

from device_snapshot_import import identity
from multi_entry_ridge import scalar, template
from neural_cell_transition import CellTransition
from reference_union_family import Reference


def import_interfaces(recipe, snapshot):
    tables = {t['name']: t for t in recipe['tables']}
    required = {a['call']['table'] for r in recipe['rules'] for a in r['query']}
    width = max(len(a['args']) for r in recipe['rules'] for a in r['query'])
    rows, seen, ids = [], set(), {}
    for row in snapshot['rows']:
        if row['table'] not in required:
            continue
        if 'subsumed' not in row:
            raise ValueError('explicit visibility required')
        if row['subsumed']:
            continue
        schema = tables[row['table']]['schema']
        if tables[row['table']]['kind'] != 'constructor' or len(schema) != len(row['values']):
            raise ValueError('constructor interfaces required')
        for value, sort in zip(row['values'], schema):
            if value['sort'] != sort['name'] or ('eq' in value) != (sort['kind'] == 'eq'):
                raise ValueError('typed interface mismatch')
        key = (row['table'], tuple(identity(v) for v in row['values']))
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        for value in row['values']:
            ids.setdefault(identity(value), len(ids))
    if not rows:
        raise ValueError('empty visible input')
    x = np.zeros((len(rows), width * 128), np.float32)
    roles = np.zeros((len(rows), width, 64), np.float32)
    labels = np.full((len(rows), width), -1, np.int32)
    pools = {name: [] for name in required}
    for i, row in enumerate(rows):
        pools[row['table']].append(i)
        schema = tables[row['table']]['schema']
        seed = dict(slots=[dict(sort=s, definition='query') for s in schema],
                    query=[dict(call=dict(table=row['table']), args=[dict(slot=j) for j in range(len(schema))])], effects=[])
        pr, _ = template(seed)
        for j, value in enumerate(row['values']):
            roles[i, j] = pr[j]
            labels[i, j] = ids[identity(value)]
        for j, value in enumerate(row['values']):
            context = roles[i, labels[i] == labels[i, j]].sum(axis=0) if 'eq' in value else scalar(value)
            x[i, j*128:(j+1)*128] = np.concatenate([roles[i, j], np.tanh(context)])
    return rows, ids, pools, x, labels, roles


def candidate_indices(pools, start, count, atoms):
    """Mixed radix enumeration on device; no bindings or matches from CPU."""
    total = math.prod(len(p) for p in pools)
    if start < 0 or count < 1 or start + count > total or total >= 2**31:
        raise ValueError('invalid candidate range or int32 capacity')
    ordinal = mx.arange(start, start + count, dtype=mx.int32)
    columns = []
    stride = total
    for pool in pools:
        stride //= len(pool)
        columns.append(mx.array(pool, dtype=mx.int32)[(ordinal // stride) % len(pool)])
    mask = [True] * len(columns) + [False] * (atoms - len(columns))
    columns += [mx.zeros(count, dtype=mx.int32)] * (atoms - len(columns))
    return mx.stack(columns, axis=1), mx.broadcast_to(mx.array(mask), (count, atoms))


def relational_edges(labels, roles, sources):
    """Exact side metadata encodes incidence, never numerical ID magnitudes."""
    values, pr = labels[sources], roles[sources]
    edges = []
    for a in range(sources.shape[1]):
        row = []
        for b in range(sources.shape[1]):
            same = (values[:, a, :, None] == values[:, b, None, :]) & (values[:, a, :, None] >= 0) & (values[:, b, None, :] >= 0)
            products = pr[:, a, :, None, :] * pr[:, b, None, :, :]
            row.append(mx.sum(same[..., None] * products, axis=(1, 2)) / mx.sqrt(mx.maximum(mx.sum(same, axis=(1, 2)), 1))[:, None])
        edges.append(mx.stack(row, axis=1))
    return mx.stack(edges, axis=1)


def binding_key(rule, chosen, rows, ids):
    """CPU audit only, called after inference; no feedback into model inputs."""
    binding = {}
    for atom, source in zip(rule['query'], chosen):
        for arg, value in zip(atom['args'], rows[int(source)]['values']):
            slot, label = arg['slot'], ids[identity(value)]
            if slot in binding and binding[slot] != label:
                return None
            binding[slot] = label
    return tuple(sorted(binding.items()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('trace', type=Path); p.add_argument('weights', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--ordered',action='store_true')
    p.add_argument('--ruleset', default='context'); p.add_argument('--snapshot-run', type=int, default=437)
    p.add_argument('--batch', type=int, default=256); p.add_argument('--candidate-limit', type=int, default=1000000)
    a = p.parse_args()
    if a.batch < 1 or a.candidate_limit < 1:
        raise ValueError('positive capacities required')
    trace = json.loads(a.trace.read_text())
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal', 'strict_audit_reference_equal', 'run_control_counts_equal')):
        raise ValueError('audited trace required')
    source = trace['recipe']; source_ids = [i for i, r in enumerate(source['rules']) if r['metadata']['source_set'] == a.ruleset]
    if not source_ids:
        raise ValueError('empty family')
    recipe = dict(source, rules=[source['rules'][i] for i in source_ids])
    if any(r.get('query_literal_guards') or any('slot' not in arg for atom in r['query'] for arg in atom['args']) for r in recipe['rules']):
        raise ValueError('slot-only family required')
    boundaries = [b['graph'] for b in trace['boundaries'] if b['ordinal'] == a.snapshot_run]
    if len(boundaries) != 1:
        raise ValueError('unique snapshot required')
    started = time.perf_counter()
    rows, ids, pools, x, labels, roles = import_interfaces(recipe, boundaries[0])
    import_seconds = time.perf_counter() - started
    if a.ordered:
        from neural_ordered_relations import OrderedCellTransition,demand,incidence
        atom_count=max(len(r['query']) for r in recipe['rules'])
        model=OrderedCellTransition(x.shape[-1],2*(atom_count*labels.shape[1])**2)
    else:
        model = CellTransition(x.shape[-1])
    model.load_weights(str(a.weights))
    started = time.perf_counter()
    labels, roles = mx.array(labels), mx.array(roles)
    tokens = model.encode(mx.array(x)); mx.eval(tokens, labels, roles)
    encode_seconds = time.perf_counter() - started
    atoms = max(len(r['query']) for r in recipe['rules']); results = []
    # Reference is evaluation only. It cannot supply candidate sources or features.
    started = time.perf_counter(); reference = Reference(recipe, rows, ids)
    reference_seconds = time.perf_counter() - started
    for rid, rule in zip(source_ids, recipe['rules']):
        pool = [pools[atom['call']['table']] for atom in rule['query']]
        total = math.prod(map(len, pool)); count = min(total, a.candidate_limit)
        _, request = template(rule)
        accepted = set(); predicted_count = fp = fn = valid_count = 0
        gpu_seconds = audit_seconds = 0.
        for start in range(0, count, a.batch):
            n = min(a.batch, count - start); began = time.perf_counter()
            ix, mask = candidate_indices(pool, start, n, atoms)
            edges = relational_edges(labels, roles, ix)
            extra={}
            if a.ordered:
                fields=mx.where(mask[...,None],labels[ix],-1)
                extra['relations']=incidence(fields,mx.array(demand(rule,atoms,labels.shape[1])),mx)
            logits, successor = model.transition(tokens[ix], edges, mask, mx.broadcast_to(mx.array(request), (n, 64)),**extra)
            mx.eval(logits, successor, ix)
            gpu_seconds += time.perf_counter() - began
            began = time.perf_counter(); predicted = np.array(logits) >= 0; chosen = np.array(ix)
            for chosen_row, pred in zip(chosen, predicted):
                key = binding_key(rule, chosen_row, rows, ids); valid = key is not None
                valid_count += valid; predicted_count += bool(pred); fp += bool(pred and not valid); fn += bool(not pred and valid)
                if pred and valid:
                    accepted.add(key)
            audit_seconds += time.perf_counter() - began
        began = time.perf_counter(); expected = {tuple(sorted(b.items())) for b in reference.matches(rule)}
        audit_seconds += time.perf_counter() - began
        item = dict(rule=rid, candidates=total, evaluated=count, unresolved_candidates=total-count,
                    valid_tuples=valid_count, accepted_tuples=predicted_count, false_positive_tuples=fp,
                    false_negative_tuples=fn, expected_matches=len(expected), recovered_matches=len(accepted & expected),
                    missed_matches=len(expected-accepted), gpu_seconds=gpu_seconds, cpu_audit_seconds=audit_seconds)
        results.append(item); print(json.dumps(item), flush=True)
    report = dict(scope='standalone first-Run seed-interface candidate audit; no effects, ownership or saturation',
                  synthetic_only_training=True, ordered_relations=a.ordered, snapshot_run=a.snapshot_run, seed_cells=len(rows),
                  initial_import_seconds=import_seconds, initial_encoding_seconds=encode_seconds,
                  cpu_reference_init_seconds=reference_seconds, groups=results,
                  weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),
                  trace_sha256=hashlib.sha256(a.trace.read_bytes()).hexdigest(),
                  limitations=['Complete type-pool Cartesian enumeration is a diagnostic, not scalable routing',
                               'All successor tokens are computed but not committed or audited in this test',
                               'No new training or promotion; counts measure matches, not mutations',
                               'GPU timing includes dispatch and first-use compilation; no speedup claim'])
    report['totals'] = {k: sum(g[k] for g in results) for k in (
        'candidates', 'evaluated', 'unresolved_candidates', 'valid_tuples',
        'accepted_tuples', 'false_positive_tuples', 'false_negative_tuples',
        'expected_matches', 'recovered_matches', 'missed_matches',
        'gpu_seconds', 'cpu_audit_seconds')}
    a.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
