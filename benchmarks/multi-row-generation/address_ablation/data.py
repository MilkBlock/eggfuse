"""Offline two-step address experiment on rows of Cells with addressable ports.

A make query at physical destination q names a source port. Its emitted Pair
must carry the named port's original address and value. A finish query names an
original port and must reference the physical slot of its generated witness.
"""
import numpy as np


VALUE_CLASSES = 4


def positive(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return int(value)


def coordinates(rows, length, ports):
    shape = tuple(positive(v, k) for v, k in zip((rows, length, ports), ('rows','length','ports')))
    return np.indices(shape, dtype=np.int32).reshape(3, -1).T.copy()


def layout(d):
    c = np.asarray(d['coords'])
    if c.ndim != 2 or c.shape[1] != 3 or not len(c) or c.dtype.kind not in 'iu' or (c < 0).any():
        raise ValueError('coords must be a nonempty integer array [ports,3]')
    rows, length, ports = map(int, c.max(0) + 1)
    if rows * length * ports != len(c) or not np.array_equal(c, coordinates(rows, length, ports)):
        raise ValueError('coords must enumerate the dense row-major (row, position, port) layout')
    return rows, length, ports


def _port_ids(refs, shape):
    refs = np.asarray(refs)
    if refs.ndim != 3 or refs.shape[-1] != 3 or refs.dtype.kind not in 'iu':
        raise ValueError('reference arrays must have integer shape [batch,slots,3]')
    if (refs < 0).any() or (refs >= np.asarray(shape)).any():
        raise ValueError('source reference outside physical layout')
    _, length, ports = shape
    r, t, p = refs.astype(np.int64).transpose(2, 0, 1)
    return ((r * length + t) * ports + p).astype(np.int32)


def _check_permutation(indices, n):
    if indices.ndim != 2 or indices.shape[1] != n or not np.all(np.sort(indices, axis=1) == np.arange(n)):
        raise ValueError('each graph must cover each physical source port exactly once')


def _targets(make, finish):
    inv = np.argsort(make, axis=1)
    return np.take_along_axis(inv, finish, axis=1).astype(np.int32)


def dataset(rows, length, ports, count, seed):
    """Build same-graph simultaneous queries; the batch dimension is independent."""
    count = positive(count, 'count')
    coords = coordinates(rows, length, ports)
    n = len(coords)
    make_rng, finish_rng, values_rng = map(np.random.default_rng, np.random.SeedSequence(seed).spawn(3))
    make = np.stack([make_rng.permutation(n) for _ in range(count)]).astype(np.int32)
    finish = np.stack([finish_rng.permutation(n) for _ in range(count)]).astype(np.int32)
    values = values_rng.integers(VALUE_CLASSES, size=(count, n), dtype=np.int32)
    # A uniform permutation task can still have randomly unique small payloads.
    # Force a payload collision only if a graph otherwise has no sibling collision;
    # choose the affected cell and ports independently of both permutations.
    if n > 1:
        for graph in values:
            grouped = graph.reshape(-1, ports) if ports > 1 else graph[None, :]
            if any(len(np.unique(cell)) < len(cell) for cell in grouped):
                continue
            cell = grouped[int(values_rng.integers(len(grouped)))]
            i, j = values_rng.choice(len(cell), size=2, replace=False)
            cell[j] = cell[i]
    return dict(coords=coords, make_ref=coords[make], finish_ref=coords[finish], value=values,
                target1=make, target2=_targets(make, finish))


def relayout(d, rows2, length2, seed):
    """Re-encode the exact same task and return old physical slot -> new slot.

    Whole Cells move to new row/sequence coordinates. Each Cell also gets an
    independent port permutation. Source rows, both sets of query destinations,
    both sets of references and both target pointer arrays share the same map.
    """
    old = layout(d)
    rows2, length2 = positive(rows2, 'rows2'), positive(length2, 'length2')
    if rows2 * length2 != old[0] * old[1]:
        raise ValueError('relayout must preserve the number of complete Cells')
    new_coords = coordinates(rows2, length2, old[2])
    n = len(new_coords)
    make, finish = (_port_ids(d[k], old) for k in ('make_ref', 'finish_ref'))
    if make.shape != finish.shape or np.shape(d['value']) != make.shape:
        raise ValueError('source values and both Run inputs require the same shape')
    for idx in (make, finish):
        _check_permutation(idx, n)
    if not np.array_equal(d['target1'], make) or not np.array_equal(d['target2'], _targets(make,finish)):
        raise ValueError('old labels contradict the source reference arrays')
    cells, ports = rows2 * length2, old[2]
    rng = np.random.default_rng(seed)
    mapping = np.empty_like(make)
    for g in range(len(make)):
        new_cells = rng.permutation(cells)
        port_map = np.stack([rng.permutation(ports) for _ in range(cells)])
        mapping[g] = (new_cells[:, None] * ports + port_map).reshape(-1)
    # The inverse only reorders addressing positions. Referenced targets still
    # go forward through mapping, including references to another row.
    inverse = np.argsort(mapping, axis=1)
    def reindex(ids):
        moved = np.take_along_axis(mapping, ids, axis=1)
        return np.take_along_axis(moved, inverse, axis=1)
    new_make, new_finish = reindex(make), reindex(finish)
    return dict(coords=new_coords, value=np.take_along_axis(d['value'], inverse, axis=1).astype(np.int32),
                make_ref=new_coords[new_make], finish_ref=new_coords[new_finish], target1=new_make,
                target2=_targets(new_make, new_finish)), mapping


def _integers(arr, shape, name):
    raw = np.asarray(arr)
    if raw.shape != shape or raw.dtype.kind not in 'iuf':
        raise ValueError(f'{name} requires discrete values with shape {shape}')
    if raw.dtype.kind == 'f' and (not np.isfinite(raw).all() or not np.equal(raw, np.trunc(raw)).all()):
        raise ValueError(f'{name} contains nonfinite or nonintegral values')
    return raw.astype(np.int64)


def _addresses(pair_origin, shape, batch, n):
    raw = np.asarray(pair_origin)
    if raw.shape == (batch,n):
        return _integers(raw, (batch,n), 'pair_origin')
    coords = _integers(raw, (batch,n,3), 'pair_origin')
    valid = ((coords >= 0) & (coords < np.asarray(shape))).all(axis=-1)
    row, pos, port = coords.transpose(2,0,1)
    return np.where(valid, (row*shape[1]+pos)*shape[2]+port, -1)


def _stage(ptr, wanted, legal, layout_shape):
    rows, length, ports = layout_shape
    batch, n = ptr.shape
    valid = (ptr>=0) & (ptr<n)
    right = ptr==wanted
    q = np.arange(n)[None, :]
    def row(x):return x//(length*ports)
    def cell(x):return x//ports
    same_cell = cell(q)==cell(wanted)
    same_row = row(q)==row(wanted)
    wrong_port = valid & ~right & (cell(ptr)==cell(wanted))
    wrong_cell = valid & (cell(ptr)!=cell(wanted))
    wrong_row = valid & (row(ptr)!=row(wanted))
    multiplicities = [np.bincount(v[ok], minlength=n) for v,ok in zip(ptr,valid)]
    record = dict(graphs=batch, obligations=batch*n, complete_graphs=int(legal.all(1).sum()),
                  correct=int(legal.sum()),pointer_correct=int(right.sum()),
                  wrong_port_right_cell=int(wrong_port.sum()),wrong_cell=int(wrong_cell.sum()),
                  wrong_position_right_row=int((wrong_cell & ~wrong_row).sum()),wrong_row=int(wrong_row.sum()),
                  invalid_pointer=int((~valid).sum()),
                  duplicates=sum(int(np.maximum(c-1,0).sum()) for c in multiplicities),
                  missing=sum(int((c==0).sum()) for c in multiplicities),
                  per_graph_correct=legal.sum(axis=1).tolist(),complete_by_graph=legal.all(axis=1).tolist())
    for name,mask in [('self',q==wanted),('sibling',same_cell & (q!=wanted)),
                      ('same_row_different_cell',same_row & ~same_cell),('same_row',same_row),('cross_row',~same_row)]:
        record[name+'_obligations']=int(mask.sum());record[name+'_correct']=int((mask&legal).sum())
        record[name+'_pointer_correct']=int((mask&right).sum())
    return record


def audit(d, ptr1, ptr2, pair_origin, pair_value, result_value):
    """Post-run CPU audit using exact correlated bindings and field ancestry.

    Wrong port/cell/row refer to the selected physical slot relative to the
    expected witness slot. Same-row/cross-row classify the required edge from
    the query to that witness. Sibling means a different port of the same Cell.
    missing/duplicates count physical pointer coverage; correct charges fields
    and ancestry as well. A correct value collision cannot redeem a wrong parent.
    """
    shape=layout(d); coords=np.asarray(d['coords']); n=len(coords)
    make=np.asarray(d['make_ref']); finish=np.asarray(d['finish_ref']); batch=len(make)
    if make.shape!=(batch,n,3) or finish.shape!=make.shape or batch==0:
        raise ValueError('expected nonempty matching Run reference tables')
    # Audit via coordinate dictionaries, independent of argsort-based labels.
    source_slots={tuple(pos):i for i,pos in enumerate(coords)}
    expected1=np.empty((batch,n),dtype=np.int64);expected2=np.empty_like(expected1);requested=np.empty_like(expected1)
    for g in range(batch):
        generated_slots={tuple(original):i for i,original in enumerate(make[g])}
        if generated_slots.keys()!=source_slots.keys() or {tuple(c) for c in finish[g]}!=source_slots.keys():
            raise ValueError('source references must be permutations of the physical ports')
        expected1[g]=[source_slots[tuple(c)] for c in make[g]]
        expected2[g]=[generated_slots[tuple(c)] for c in finish[g]]
        requested[g]=[source_slots[tuple(c)] for c in finish[g]]
    if not np.array_equal(d['target1'],expected1) or not np.array_equal(d['target2'],expected2):
        raise ValueError('dataset labels disagree with the source-coordinate interpreter')
    ptr1=_integers(ptr1,(batch,n),'ptr1');ptr2=_integers(ptr2,(batch,n),'ptr2')
    origin=_addresses(pair_origin,shape,batch,n)
    def scalar(value,name):
        x=np.asarray(value)
        return _integers(x[...,0] if x.shape==(batch,n,1) else x,(batch,n),name)
    values=scalar(d['value'],'source values');first=scalar(pair_value,'pair_value');second=scalar(result_value,'result_value')
    g=np.arange(batch)[:,None];p1=np.clip(ptr1,0,n-1);p2=np.clip(ptr2,0,n-1)
    valid1=(p1==ptr1);valid2=(p2==ptr2)
    origin_bound=valid1 & (origin==ptr1);value_bound=valid1 & (first==values[g,p1]);legal1=(ptr1==expected1)&origin_bound&value_bound
    wanted_parent_ready=legal1[g,expected2];selected_parent_legal=valid2&legal1[g,p2]
    selected_origin_ok=valid2 & (origin[g,p2]==requested)
    returned_value_ok=second==values[g,requested]
    payload_bound=valid2 & (second==first[g,p2])
    legal2=(ptr2==expected2)&selected_parent_legal&selected_origin_ok&returned_value_ok&payload_bound
    stage1=_stage(ptr1,expected1,legal1,shape);stage2=_stage(ptr2,expected2,legal2,shape)
    stage1.update(origin_matches_selected=int(origin_bound.sum()),value_matches_selected=int(value_bound.sum()))
    stage2.update(parent_ready_obligations=int(wanted_parent_ready.sum()),correct_given_parent=int((wanted_parent_ready&legal2).sum()),
                  graphs_with_all_parents_ready=int(wanted_parent_ready.all(1).sum()),complete_when_parents_ready=int((wanted_parent_ready.all(1)&legal2.all(1)).sum()),
                  unavailable_required_parents=int((~wanted_parent_ready).sum()),selected_illegal_or_absent_parent=int((~selected_parent_legal).sum()),
                  selected_origin_correct=int(selected_origin_ok.sum()),value_correct=int(returned_value_ok.sum()),
                  wrong_parent_value_looks_right=int(((ptr2!=expected2)&returned_value_ok).sum()),
                  wrong_requested_origin_right_cell=int((valid2 & (origin[g,p2]>=0) & (origin[g,p2]<n) & ~selected_origin_ok & (origin[g,p2]//shape[2]==requested//shape[2])).sum()),
                  result_bound_to_selected=int(payload_bound.sum()))
    return dict(graphs=batch,obligations_per_run=batch*n,whole_graphs=int((legal1.all(1)&legal2.all(1)).sum()),run1=stage1,run2=stage2)
