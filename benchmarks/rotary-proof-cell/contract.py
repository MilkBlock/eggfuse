"""Independent finite semantic teacher/checker. Never imported by the GPU model.

The closed universe has Seed(a,b), optional SameValue(a,b), optional initial a=b,
F(a)=u, F(b)=v, and (only after the repeated-variable LHS matches) G(u)=w.
The annotation is opaque Cell metadata, not an attribute of an e-class.
"""
import numpy as np
from schema import SPECS, PAIRS, OFFSETS, CATEGORICAL, DIM


def labels(case):
    initial, same, free, tag = map(int, case)
    payload = [(tag >> bit) & 1 for bit in range(8)]
    out = []
    for stage in (1, 2, 3):
        equal = bool(initial or (stage >= 2 and same))
        transferred = stage == 3 and equal
        layout = [0, 1, 2, 3]
        if transferred: layout.insert(free, 4)
        else: layout.append(5)
        alias = [layout.index(role) for role in range(4)]
        eq = [int(equal and (i, j) in ((0, 1), (2, 3))) for i, j in PAIRS]
        if stage == 1: proof, refs = 0, [0, 4 if initial else 5, 5]
        elif stage == 2:
            proof, refs = (1, [1, 2, 5]) if same else (2, [2, 4 if initial else 5, 5])
        elif transferred: proof, refs = 3, [0, 2, 3 if same else 4]
        else: proof, refs = 4, [0, 2, 5]
        out.append(dict(layout=layout, alias=alias, owner=[2 if transferred else 1], proof=[proof], premises=refs,
                        g_arg=[2 if transferred else 5], eq=eq, pending=[int(stage == 1 and same), int(not transferred)],
                        retired=[int(transferred)], payload=payload))
    return out


def seed_inputs(cases):
    cases = np.asarray(cases, np.int32)
    seed = np.concatenate((cases[:, :2].astype(np.float32), np.eye(5, dtype=np.float32)[cases[:, 2]],
                           ((cases[:, 3, None] >> np.arange(8)) & 1).astype(np.float32)), axis=1)
    return seed


def batch(cases):
    cases = np.asarray(cases, np.int32)
    seed = seed_inputs(cases)
    truth = [labels(c) for c in cases]
    targets = {k: np.array([[t[s][k] for t in truth] for s in range(3)], np.int32) for k in SPECS}
    return seed, targets


def partition(header):
    parent = list(range(5))
    def root(x):
        while parent[x] != x: x = parent[x]
        return x
    for yes, (i, j) in zip(header['eq'], PAIRS):
        if yes: parent[root(j)] = root(i)
    return [root(i) for i in range(5)]


def reference(case, stage):
    """Independent symbolic rule execution and congruence closure on five roles."""
    initial, same, _, _ = map(int, case)
    parents = list(range(5))
    def root(x):
        while parents[x] != x: x = parents[x]
        return x
    def union(a, b):
        a, b = root(a), root(b)
        if a == b: return False
        parents[max(a, b)] = min(a, b)
        return True
    if initial: union(0, 1)
    constructors = [('F', (0,), 2), ('F', (1,), 3)]
    if stage >= 2 and same: union(0, 1)
    def close():
        changed = True
        while changed:
            changed = False; keys = {}
            for op, args, dst in constructors:
                key = (op, tuple(root(a) for a in args))
                if key in keys: changed = union(dst, keys[key]) or changed
                else: keys[key] = dst
    close()
    # Exact repeated-variable LHS: Seed(x,x) and an F(x) witness.
    enabled = stage == 3 and root(0) == root(1)
    if enabled: constructors.append(('G', (2,), 4)); close()
    return dict(roots=[root(i) for i in range(5)], constructors=constructors,
                extend_enabled=enabled, roles=[0,1,2,3,4] if enabled else [0,1,2,3])


def verify(case, headers, owner_metadata=None, reads=None):
    """Check proof premises and every published view; do not correct any output."""
    initial, same, free, tag = map(int, case)
    errors = []
    for s, h in enumerate(headers, 1):
        # Trusted input facts and source schedule determine authorized equality.
        expected = reference(case, s)
        allowed_eq = expected['roots'][0] == expected['roots'][1]
        expected_pairs = {(i, j) for i, j in PAIRS if i in expected['roles'] and j in expected['roles'] and expected['roots'][i] == expected['roots'][j]}
        actual_pairs = {p for yes, p in zip(h['eq'], PAIRS) if yes}
        if actual_pairs != expected_pairs: errors.append((s, 'unproved_or_missing_equality'))
        parent = partition(h)
        if s == 1:
            if h['proof'] != [0] or h['premises'] != [0, 4 if initial else 5, 5]: errors.append((s, 'build_certificate'))
        elif s == 2:
            wanted = (1, [1, 2, 5]) if same else (2, [2, 4 if initial else 5, 5])
            if h['proof'] != [wanted[0]] or h['premises'] != wanted[1]: errors.append((s, 'union_certificate'))
        else:
            wanted = (3, [0, 2, 3 if same else 4]) if allowed_eq else (4, [0, 2, 5])
            if h['proof'] != [wanted[0]] or h['premises'] != wanted[1]: errors.append((s, 'extend_certificate'))
        transfer = s == 3 and allowed_eq
        if h['owner'] != [2 if transfer else 1] or h['retired'] != [int(transfer)]: errors.append((s, 'owner_or_retirement'))
        if owner_metadata is not None and owner_metadata[s - 1] != h['owner'][0]: errors.append((s, 'token_owner_binding'))
        live = [r for r in h['layout'] if r != 5]
        if sorted(live) != ([0, 1, 2, 3, 4] if transfer else [0, 1, 2, 3]): errors.append((s, 'lost_or_invented_member'))
        if transfer:
            if h['layout'][free] != 4: errors.append((s, 'requested_result_port'))
            # LHS Seed(x,x) is valid only modulo an authorized Eq proof.
            if parent[0] != parent[1]: errors.append((s, 'lhs_repeated_variable'))
            if h['g_arg'][0] not in (2, 3) or parent[h['g_arg'][0]] != parent[2]: errors.append((s, 'G_argument'))
        elif h['g_arg'] != [5]: errors.append((s, 'early_or_unsupported_G'))
        for old, new in enumerate(h['alias']):
            if not 0 <= new < 5 or h['layout'][new] != old: errors.append((s, 'old_port_projection'))
        if h['pending'] != [int(s == 1 and same), int(not transfer)]: errors.append((s, 'lost_obligation'))
        if h['payload'] != [(tag >> b) & 1 for b in range(8)]: errors.append((s, 'lost_annotation'))
    if reads is not None:
        if not reads['valid'] or reads['roles'] != [0, 1, 2, 3]: errors.append((3, 'retired_interface_read'))
        if reads['payload'] != [(tag >> b) & 1 for b in range(8)]: errors.append((3, 'retired_annotation'))
        if reads['eq'] != headers[2]['eq']: errors.append((3, 'inconsistent_read_view'))
    return errors


def cpu_unrotate(token, position, axis='cell'):
    # Independent double-precision evaluation on the actual saved float32 bytes.
    out = np.array(token, np.float64, copy=True)
    start = 0 if axis == 'cell' else DIM // 2
    freq = np.exp(-np.log(10000.) * np.arange(DIM // 4) / (DIM // 4)).astype(np.float32).astype(np.float64)
    angle = -(np.asarray(position, np.float32)[..., None] * freq.astype(np.float32)).astype(np.float64)
    part = out[..., start:start + DIM // 2].copy()
    a, b = part[..., 0::2], part[..., 1::2]
    out[..., start:start + DIM // 2:2] = np.cos(angle) * a - np.sin(angle) * b
    out[..., start + 1:start + DIM // 2:2] = np.sin(angle) * a + np.cos(angle) * b
    return out


def cpu_decode(tokens, positions, weight, bias):
    logits = cpu_unrotate(tokens, positions) @ np.asarray(weight, np.float64).T + np.asarray(bias, np.float64)
    result = {}
    for k, (a, b) in OFFSETS.items():
        v = logits[..., a:b].reshape(logits.shape[:-1] + SPECS[k])
        result[k] = np.argmax(v, axis=-1) if k in CATEGORICAL else (v >= 0).astype(np.int32)
    return result, logits


def headers_at(decoded, i):
    return [{k: decoded[k][s, i].tolist() for k in SPECS} for s in range(3)]


def decoded_host(logits):
    out = {}
    for k, (a, b) in OFFSETS.items():
        v = logits[..., a:b].reshape(logits.shape[:-1] + SPECS[k])
        out[k] = np.argmax(v, axis=-1) if k in CATEGORICAL else (v >= 0).astype(np.int32)
    return out


def audit_result(cases, positions, result, weight, bias):
    """CPU-only audit of saved bytes; emits a verdict, never a replacement state."""
    decoder, cpu_logits = cpu_decode(result['tokens'], result['locations'], weight, bias)
    gpu = decoded_host(result['logits'])
    decoder_equal = all(np.array_equal(decoder[k], gpu[k]) for k in SPECS)
    owners = result['owners']
    in_range = np.all((owners >= 0) & (owners < 3))
    locations_bound = bool(in_range and np.array_equal(result['locations'],
        np.take_along_axis(np.broadcast_to(positions, (3,) + positions.shape),
                           np.clip(owners, 0, 2)[..., None], axis=-1)[..., 0]))
    finite = bool(all(np.isfinite(result[k]).all() for k in
                      ('tokens', 'logits', 'rebased_keys', 'direct_keys')))
    rotary_error = float(np.max(np.abs(result['rebased_keys'] - result['direct_keys'])))
    errors, examples, passed = {}, [], 0
    for i, case in enumerate(cases):
        headers = headers_at(decoder, i)
        reads = dict(valid=bool(result['read_valid'][i]), roles=result['read_roles'][i].tolist(),
                     payload=result['read_payload'][i].tolist(), eq=result['read_eq'][i].tolist())
        wrong = verify(case, headers, owners[:, i].tolist(), reads)
        if result['read_ports'][i].tolist() != headers[2]['alias']:
            wrong.append((3, 'rotary_port_projection'))
        passed += not wrong
        for _, reason in set(wrong): errors[reason] = errors.get(reason, 0) + 1
        if wrong and len(examples) < 5:
            examples.append(dict(case=case.tolist(), errors=wrong, headers=headers))
    return dict(cases=len(cases), passed=int(passed), errors=errors, examples=examples,
                accepted=bool(passed == len(cases) and decoder_equal and locations_bound and finite and rotary_error < 1e-6),
                cpu_gpu_decoder_equal=decoder_equal, owner_positions_bound=locations_bound, finite=finite,
                decoder_max_abs_difference=float(np.max(np.abs(cpu_logits - result['logits']))),
                rotary_rebase_max_error=rotary_error)
