"""Bounded, template-only Eq state enumeration and dense GPU projection.

Candidates are type-compatible partitions, not proofs of reachable completion.
No observed target participates in compilation. Scalars and stable IDs stay in
their existing slots; this module only represents the local equality component.
"""
import itertools
import numpy as np
from token_eq_readout import pair_layout, static_equalities, quotient_layout
from device_semantic_template import template


def partitions(n):
    """Canonical restricted-growth strings, finest partition first."""
    if not n:
        yield ()
        return
    def visit(prefix):
        if len(prefix) == n:
            yield tuple(prefix)
        else:
            for label in reversed(range(max(prefix) + 2)):
                yield from visit(prefix + [label])
    yield from visit([0])


def compile_states(rule, limit=4096):
    if limit < 1:
        raise ValueError('positive state budget required')
    pairs = pair_layout(rule)[0]
    static = static_equalities(rule, pairs)
    quotient = quotient_layout(rule, pairs, static)
    eq = {i: s['sort']['name'] for i, s in enumerate(rule['slots'])
          if s['sort']['kind'] == 'eq'}
    parent = {i: i for i in eq}
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for (a, b), yes in zip(pairs, static):
        if yes:
            parent[root(b)] = root(a)
    groups = {}
    for i, sort in eq.items():
        groups.setdefault(sort, set()).add(root(i))
    layouts = [sorted(g) for g in groups.values()]
    choices = []
    size = 1
    for layout in layouts:
        # Abort during enumeration, before a large Bell-number allocation.
        values = list(itertools.islice(partitions(len(layout)), limit // size + 1))
        if len(values) * size > limit:
            raise ValueError('Cell Eq state budget exceeded; retain fallback')
        choices.append(values)
        size *= len(values)
    states = []
    for combination in itertools.product(*choices):
        labels = {r: (g, c) for g, (layout, part) in enumerate(zip(layouts, combination))
                  for r, c in zip(layout, part)}
        states.append([labels[root(a)] == labels[root(b)] for a, b in pairs])
    full = np.array(states, bool).reshape(size, len(pairs))
    dynamic = full[:, quotient['representatives']].astype(np.float32)
    # Prefer fewer additional equalities for exact score ties, then canonical order.
    order = np.argsort(dynamic.sum(axis=1), kind='stable')
    return dict(states=dynamic[order], full=full[order], static=static,
                pairs=pairs, quotient=quotient)


def project(scores, states, required, xp):
    """Closest binary state by squared error; fixed matmul, mask, argmax, gather.

    required is current proven equality in quotient-pair order. All-merged
    same-sort state guarantees a candidate for any well-shaped required mask.
    Caller validates finite scores and template/layout identity at its boundary.
    """
    utility = (2 * scores - 1) @ xp.swapaxes(states, -1, -2)
    conflicts = required.astype(xp.float32) @ xp.swapaxes(1 - states, -1, -2)
    utility = xp.where(conflicts == 0, utility, -float('inf'))
    chosen = xp.argmax(utility, axis=1)
    return states[chosen], chosen


def compile_tokens(rule, plan):
    """Bake equality moments; leave actual scalar values dynamic.

    Requires a completed semantic layout. No ID-derived floating values and no
    per-instance alias graph. This is a representation, not a completion proof.
    """
    roles, _ = template(rule)
    eq = [i for i, s in enumerate(rule['slots']) if s['sort']['kind'] == 'eq']
    scalar = [i for i in range(len(roles)) if i not in eq]
    first, second, counts = [], [], []
    for state in plan['full']:
        parent = {i: i for i in eq}
        def root(i):
            while parent[i] != i:
                i = parent[i]
            return i
        for (a, b), yes in zip(plan['pairs'], state):
            if yes:
                parent[root(b)] = root(a)
        groups = {}
        for i in eq:
            groups.setdefault(root(i), []).append(i)
        one = np.zeros(roles.shape[1], np.float32)
        two = one.copy()
        for members in groups.values():
            message = np.tanh(roles[members] + roles[members].mean(axis=0))
            one += message.mean(axis=0)
            two += (message * message).mean(axis=0)
        first.append(one);second.append(two);counts.append(len(groups))
    return dict(first=np.array(first), second=np.array(second),
                counts=np.array(counts,np.float32), scalar_slots=np.array(scalar,np.int32),
                scalar_roles=roles[scalar])


def tokens(chosen, scalar_codes, plan, xp):
    message = xp.tanh(plan['scalar_roles'][None, :, :] + scalar_codes)
    first = plan['first'][chosen] + xp.sum(message, axis=1)
    second = plan['second'][chosen] + xp.sum(message * message, axis=1)
    count = xp.maximum(plan['counts'][chosen] + scalar_codes.shape[1], 1)
    return xp.tanh(xp.concatenate([first / xp.sqrt(count[:, None]), second / count[:, None]], axis=1))
