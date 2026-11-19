"""Offline source tables and unordered labels for the two-Run experiment."""
from collections import defaultdict
from functools import lru_cache
from itertools import combinations_with_replacement

import numpy as np


SPLITS = {
    'train': (4096, 82101),
    'iid': (256, 82102),
    'left_collision': (256, 82103),
    'right_collision': (256, 82104),
}
CAPACITY = 8


def bindings(a, b):
    return [(i, j) for i in range(4) for j in range(4) if a[i, 0] == b[j, 0]]


@lru_cache(maxsize=3)
def patterns(family):
    """Select multiplicities first so dense joins and empty graphs both occur."""
    multisets = list(combinations_with_replacement(range(6), 4))
    banks = defaultdict(list)
    for left in multisets:
        lc = np.bincount(left, minlength=6)
        for right in multisets:
            rc = np.bincount(right, minlength=6)
            count = int(lc @ rc)
            if count > CAPACITY:
                continue
            if family == 'left_collision' and not np.any((lc >= 2) & (rc > 0)):
                continue
            if family == 'right_collision' and not np.any((rc >= 2) & (lc > 0)):
                continue
            banks[count].append((left, right))
    return banks


def table(keys, rng):
    shuffled = rng.permutation(keys)
    values = np.empty(4, dtype=np.int32)
    for key in np.unique(shuffled):
        locations = np.flatnonzero(shuffled == key)
        values[locations] = rng.choice(4, len(locations), replace=False)
    return np.stack((shuffled, values), axis=-1).astype(np.int32)


def make_inputs(rng, bank, family):
    left, right = bank[int(rng.integers(len(bank)))]
    key_names = rng.permutation(8)
    a = table(key_names[list(left)], rng)
    b = table(key_names[list(right)], rng)
    if family == 'plain':
        return a, b, None

    duplicates, partners = (a, b) if family == 'left_collision' else (b, a)
    keys, counts = np.unique(duplicates[:, 0], return_counts=True)
    eligible = [k for k, n in zip(keys, counts) if n >= 2 and k in partners[:, 0]]
    key = rng.choice(eligible)
    first, second = rng.choice(np.flatnonzero(duplicates[:, 0] == key), 2, replace=False)
    duplicates[second, 1] = duplicates[first, 1]
    partner = rng.choice(np.flatnonzero(partners[:, 0] == key))
    twins = [(int(i), int(partner)) for i in (first, second)]
    if family == 'right_collision':
        twins = [(j, i) for i, j in twins]
    return a, b, twins


def take(rng, entries, count):
    return [entries[i] for i in rng.choice(len(entries), count, replace=False)]


def make_requests(rng, legal, twins):
    illegal = [(i, j) for i in range(4) for j in range(4) if (i, j) not in legal]
    if twins is None:
        n = int(rng.integers(min(len(legal), 4) + 1))
        choices = take(rng, legal, n) + take(rng, illegal, 4 - n)
    else:
        remaining = [pair for pair in legal if pair not in twins]
        n = int(rng.integers(min(len(remaining), 2) + 1))
        choices = [twins[0], *take(rng, remaining, n), *take(rng, illegal, 3 - n)]
    records = np.column_stack((choices, rng.integers(4, size=4))).astype(np.int32)
    order = rng.permutation(4)
    if twins is None:
        return [records[order]]
    variant = records.copy()
    variant[0, :2] = twins[1]
    return [records[order], variant[order]]


def labels(a, b, requests):
    pair = np.zeros((CAPACITY, 6), dtype=np.int32)
    result = np.zeros_like(pair)
    matches = bindings(a, b)
    if len(matches) > CAPACITY:
        raise ValueError('reference graph exceeds output capacity')
    for slot, (i, j) in enumerate(matches):
        pair[slot] = [1, i, j, *a[i], b[j, 1]]
    # Lexicographic source identity is independent of Request token position.
    selected = sorted((int(i), int(j), int(t)) for i, j, t in requests if (i, j) in matches)
    for slot, (i, j, tag) in enumerate(selected):
        result[slot] = [1, i, j, tag, a[i, 1], b[j, 1]]
    return pair, result


def dataset(split):
    """Return fresh int32 arrays. Held-out consecutive samples are twin requests."""
    size, seed = SPLITS[split]
    family = split if split.endswith('collision') else 'plain'
    rng = np.random.default_rng(seed)
    banks = patterns(family)
    sizes = sorted(banks)
    records = []
    seen = set()
    while len(records) < size:
        group = len(records) // (2 if family != 'plain' else 1)
        bank = banks[sizes[group % len(sizes)]]
        a, b, twins = make_inputs(rng, bank, family)
        requests = make_requests(rng, bindings(a, b), twins)
        keys = [a.tobytes() + b.tobytes() + req.tobytes() for req in requests]
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        for req in requests:
            records.append((a, b, req, *labels(a, b, req)))
    return {name: np.stack(column) for name, column in zip(
        ('a', 'b', 'requests', 'target1', 'target2'), zip(*records))}
