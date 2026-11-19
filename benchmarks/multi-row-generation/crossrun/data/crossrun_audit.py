"""Independent NumPy post-run audit. Inputs are actual tokens and source data."""
from collections import Counter

import numpy as np


def outputs(raw, batch):
    arrays = {k: np.asarray(raw[k]) for k in ('active', 'pointers', 'fields')}
    for name, trailing in (('active', ()), ('pointers', (2,)), ('fields', (3,))):
        arr = arrays[name]
        if arr.shape != (batch, 8, *trailing) or arr.dtype.kind not in 'biu':
            raise ValueError(f'{name} requires discrete shape {(batch, 8, *trailing)}')
    if not np.isin(arrays['active'], (0, 1)).all():
        raise ValueError('active must contain only zero or one')
    return arrays


def score(expected, bound, semantic, active, field_errors, parent_errors):
    missing = len(expected - set(bound))
    semantic_missing = len(expected - set(semantic))
    duplicate = sum(count - 1 for count in bound.values())
    illegal = active - sum(bound.values())
    binding_complete = not (missing or duplicate or illegal)
    return dict(nonempty=bool(expected), obligations=len(expected), active_outputs=active,
                valid_bindings=sum(bound.values()), valid_unique=len(bound),
                semantic_unique=len(semantic), duplicates=duplicate, missing=missing,
                semantic_missing=semantic_missing, illegal=illegal, field_errors=field_errors,
                parent_field_errors=parent_errors, binding_complete=binding_complete,
                complete=binding_complete and not (field_errors or parent_errors))


def aggregate(report):
    numeric = ('obligations', 'active_outputs', 'valid_bindings', 'valid_unique',
               'semantic_unique', 'duplicates', 'missing', 'semantic_missing', 'illegal',
               'field_errors', 'parent_field_errors')
    return dict(graphs=len(report), complete_graphs=sum(g['complete'] for g in report),
                binding_complete_graphs=sum(g['binding_complete'] for g in report),
                nonempty_graphs=sum(g['nonempty'] for g in report),
                nonempty_complete_graphs=sum(g['nonempty'] and g['complete'] for g in report),
                nonempty_binding_complete_graphs=sum(g['nonempty'] and g['binding_complete'] for g in report),
                **{k: sum(g[k] for g in report) for k in numeric}, per_graph=report)


def audit(a, b, requests, first, second):
    """Check the decoded witness identities before checking projected output values.

    A source obligation exists exactly once per original (i,j) pair. A second
    token must consume an active first token referring to that same (i,j) and
    the Request record for it. Selecting a different, equal-valued parent is
    illegal. Complete semantics requires a valid field payload throughout the
    selected ancestry, including the consumed parent. Unrelated Run1 failures
    do not invalidate a Run2 graph if every required Run2 lineage is exact.
    """
    a, b, requests = (np.asarray(v) for v in (a, b, requests))
    batch = len(a)
    if a.shape != (batch, 4, 2) or a.shape != b.shape or requests.shape != (batch, 4, 3):
        raise ValueError('source table shapes differ from contract')
    first, second = outputs(first, batch), outputs(second, batch)
    reports = [[], []]
    for g in range(batch):
        table = {(i, j): (int(key), int(x), int(y))
                 for i, (key, x) in enumerate(a[g])
                 for j, (other, y) in enumerate(b[g]) if key == other}
        request_rows = [tuple(map(int, row)) for row in requests[g]]
        if len({(i, j) for i, j, _ in request_rows}) != 4:
            raise ValueError('Request identities must be unique')
        expected2 = {(i, j): (tag, *table[i, j][1:]) for i, j, tag in request_rows if (i, j) in table}
        bound, semantic = Counter(), Counter()
        parent = {}
        field_errors = 0
        for s in np.flatnonzero(first['active'][g]):
            identity = tuple(map(int, first['pointers'][g, s]))
            if identity not in table:
                continue
            bound[identity] += 1
            exact = tuple(first['fields'][g, s]) == table[identity]
            parent[s] = (identity, exact)
            if exact:
                semantic[identity] += 1
            else:
                field_errors += 1
        reports[0].append(score(set(table), bound, semantic, int(first['active'][g].sum()), field_errors, 0))

        unavailable_parents = len(set(expected2) - set(semantic))
        bound, semantic = Counter(), Counter()
        field_errors = parent_errors = 0
        for s in np.flatnonzero(second['active'][g]):
            slot, ri = map(int, second['pointers'][g, s])
            if slot not in parent or not 0 <= ri < len(request_rows):
                continue
            identity, parent_exact = parent[slot]
            if identity != request_rows[ri][:2]:
                continue
            bound[identity] += 1
            field_exact = tuple(second['fields'][g, s]) == expected2[identity]
            field_errors += not field_exact
            parent_errors += not parent_exact
            if field_exact and parent_exact:
                semantic[identity] += 1
        run2_graph = score(set(expected2), bound, semantic, int(second['active'][g].sum()),
                           field_errors, parent_errors)
        run2_graph['unavailable_parent_obligations'] = unavailable_parents
        reports[1].append(run2_graph)
    run2 = aggregate(reports[1])
    ready = [g for g in reports[1] if g['nonempty'] and not g['unavailable_parent_obligations']]
    run2['parent_ready_nonempty_graphs'] = len(ready)
    run2['parent_ready_nonempty_complete_graphs'] = sum(g['complete'] for g in ready)
    run2['unavailable_parent_obligations'] = sum(g['unavailable_parent_obligations'] for g in reports[1])
    return dict(run1=aggregate(reports[0]), run2=run2,
                both_complete_graphs=sum(a['complete'] and b['complete'] for a, b in zip(*reports)))


def audit_twins(a, b, requests, first, second):
    """Test whether the selected Pair slot follows the changed recipient address."""
    a, b, requests = map(np.asarray, (a, b, requests))
    if len(a) % 2:
        raise ValueError('expected consecutive twin pairs')
    np.testing.assert_array_equal(a[::2], a[1::2]);np.testing.assert_array_equal(b[::2], b[1::2])
    np.testing.assert_array_equal(requests[::2, :, 2], requests[1::2, :, 2])
    first, second = outputs(first, len(a)), outputs(second, len(a))
    # The Run 1 source does not include Request. Its generated discrete trace
    # must agree on both twins before sharing a physical Pair position has meaning.
    for value in first.values():
        np.testing.assert_array_equal(value[::2], value[1::2])
    rows = (requests[::2, :, :2] != requests[1::2, :, :2]).any(-1)
    if not (rows.sum(-1) == 1).all():
        raise ValueError('expected exactly one changed request per pair')
    count = Counter()
    for pair_index, rq in enumerate(rows.argmax(-1)):
        selected = []
        exact = []
        for g in (2*pair_index, 2*pair_index+1):
            i, j, tag = requests[g, rq]
            emissions = np.flatnonzero((second['active'][g] == 1) & (second['pointers'][g, :, 1] == rq))
            count['missing_emissions'] += int(len(emissions) == 0)
            count['extra_emissions'] += max(0, len(emissions) - 1)
            if len(emissions) != 1:
                selected.append(None);exact.append(False);continue
            out = emissions[0]
            pi = int(second['pointers'][g, out, 0]);selected.append(pi)
            valid = (0 <= pi < 8 and first['active'][g, pi] == 1 and
                     tuple(first['pointers'][g, pi]) == (i, j) and
                     a[g, i, 0] == b[g, j, 0])
            count['correct_parent_emissions'] += int(valid)
            valid = (valid and tuple(first['fields'][g, pi]) == (*a[g, i], b[g,j,1]) and
                     tuple(second['fields'][g,out]) == (tag, a[g,i,1], b[g,j,1]))
            exact.append(bool(valid))
        count['both_emitted_once'] += int(None not in selected)
        count['both_emitted_once_same_parent_slot'] += int(None not in selected and selected[0] == selected[1])
        count['both_counterfactual_claims_exact'] += int(all(exact))
    return dict(twin_pairs=len(a)//2, changed_request_instances=len(a), **dict(count))
