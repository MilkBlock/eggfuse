#!/usr/bin/env python3
"""Exact rooted-state comparison for changed recipes, plus short work counters.

Propagate a bijection through complete function keys, then verify every row,
sort, scalar, visibility bit and fixed initial port. Unresolved/unrooted graphs
fail closed; this is not a hash-only graph-equivalence test or a timing harness.
"""
import argparse
import hashlib
import json
from itertools import zip_longest
from pathlib import Path


def load(p):
    return json.loads(Path(p).read_text())


def key(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'))


def states(path):
    """Stream a JSON array of snapshots instead of retaining gigabytes of rows."""
    decoder = json.JSONDecoder()
    with path.open() as f:
        buf = ''
        eof = False
        while True:
            buf = buf.lstrip()
            if buf[:1] in ('[', ','):
                buf = buf[1:].lstrip()
            if buf.startswith(']'):
                assert not buf[1:].strip() and not f.read().strip()
                return
            try:
                state, end = decoder.raw_decode(buf)
            except json.JSONDecodeError:
                assert not eof, 'truncated stage snapshot'
                chunk = f.read(1024 * 1024)
                eof = not chunk
                buf += chunk
                continue
            # Repeated snapshots reuse a previously verified exact bijection.
            digest = hashlib.sha256(buf[:end].encode()).hexdigest()
            yield state, digest
            buf = buf[end:]


def equivalent(left, right, tables=None, anchors=True):
    rows = lambda s: [r for r in s['rows'] if tables is None or r['table'] in tables]
    aa, bb = rows(left), rows(right)
    assert len(aa) == len(bb), ('row counts', len(aa), len(bb))
    forward, inverse = {}, {}

    def bind(a, b):
        assert a['sort'] == b['sort'], ('sort', a, b)
        if 'eq' in a:
            assert 'eq' in b, (a, b)
            a, b = key(a), key(b)
            assert a not in forward or forward[a] == b, ('conflicting image', a, b)
            assert b not in inverse or inverse[b] == a, ('non-bijective image', a, b)
            forward[a], inverse[b] = b, a
        else:
            assert mapped(a) == canonical(b), ('scalar/container result', a, b)

    def canonical(v):
        if isinstance(v, dict):
            return {k: sorted((canonical(x) for x in vv), key=key) if k == 'elements'
                    else canonical(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [canonical(x) for x in v]
        return v

    def mapped(v):
        if isinstance(v, dict):
            if 'eq' in v:
                return json.loads(forward[key(v)])
            return {k: sorted((mapped(x) for x in vv), key=key) if k == 'elements'
                    else mapped(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [mapped(x) for x in v]
        return v

    if anchors:
        ports = lambda s: {(p['sort'], p['old']): p['now'] for p in s['anchors']}
        ap, bp = ports(left), ports(right)
        assert ap.keys() == bp.keys(), 'initial ports differ'
        for (sort, old), now in ap.items():
            bind({'sort': sort, 'eq': now}, {'sort': sort, 'eq': bp[sort, old]})
    index = {}
    for r in bb:
        k = key([r['table'], canonical(r['values'][:-1])])
        assert k not in index, ('duplicate complete key', k)
        index[k] = r
    todo = aa
    while todo:
        rest = []
        for r in todo:
            try:
                args = mapped(r['values'][:-1])
                other = index[key([r['table'], args])]
                bind(r['values'][-1], other['values'][-1])
            except KeyError:
                rest.append(r)
        assert len(rest) < len(todo), ('unresolved or unequal state', len(rest))
        todo = rest
    assert sorted(key(mapped(r)) for r in aa) == sorted(key(canonical(r)) for r in bb), 'full row/visibility mismatch'
    return {'rows': len(aa), 'eq_values': len(forward), 'exact_bijection': True}


def main(root):
    result = {'scope': 'standalone Cell CPU; paired source rewrite without a learned catalog; no timing claim', 'lanes': {}}
    reports = {}
    for mode in ('legacy', 'values'):
        artifact = root / f'sum-{mode}'
        directory = root / f'run-{mode}'
        r = reports[mode] = load(directory / 'report.json')
        assert r['status'] == 'complete'
        result['lanes'][mode] = {
            'files': {name: hashlib.sha256((artifact / name).read_bytes()).hexdigest()
                      for name in ('source_sk_mk.egg', 'program.json', 'marker-selection.json')},
            'key_lookup_calls': r['key_lookup_calls'],
            'execute_allocations': r['allocations'], 'setup_allocations': r['setup_allocations'],
            'entry_schedule': r['entry_schedule']['stats'],
            'stage_spine': r['stage_spine']['stats'],
        }
    fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    schedules = [[[s[k] for k in fields] for s in reports[mode]['steps']] for mode in ('legacy', 'values')]
    assert schedules[0] == schedules[1], 'ordered Runs differ'
    result['runs'] = len(schedules[0])
    result['schedule_sha256'] = hashlib.sha256(key(schedules[0]).encode()).hexdigest()
    result['final_state'] = equivalent(*(load(root / f'run-{m}/state.json') for m in ('legacy', 'values')))
    stage_paths = [root / f'stages-{m}/stages.json' for m in ('legacy', 'values')]
    if all(p.exists() for p in stage_paths):
        cache = {}
        proofs = []
        for aa, bb in zip_longest(*(states(p) for p in stage_paths)):
            assert aa is not None and bb is not None, 'different stage counts'
            a, ah = aa
            b, bh = bb
            if (ah, bh) not in cache:
                cache[ah, bh] = equivalent(a, b)
            proofs.append(cache[ah, bh])
        assert len(proofs) == result['runs']
        result['stage_bijections'] = {'checked': len(proofs), 'all_exact': True,
                                    'proof_counts_sha256': hashlib.sha256(key(proofs).encode()).hexdigest()}
        result['distinct_stage_pairs'] = len(cache)
    native_paths = [root / f'native-{m}.json' for m in ('source', 'legacy', 'values')]
    if all(p.exists() for p in native_paths):
        native = [load(p) for p in native_paths]
        tables = {r['table'] for r in native[0]['rows']}
        result['native_marker_equivalence'] = equivalent(native[1], native[2], anchors=False)
        def check(a, b, selected=None):
            try:
                return {'status': 'equivalent', **equivalent(a, b, selected, False)}
            except AssertionError as e:
                return {'status': 'different', 'witness': str(e)}
        # Preserve failed independent controls. Agreement between the two
        # rewrite modes does not certify the complete legacy toolchain.
        result['native_source_projection'] = [check(native[0], n, tables) for n in native[1:]]
        result['native_vs_cpu'] = [check(native[i+1], load(root / f'run-{m}/state.json'))
                                   for i, m in enumerate(('legacy', 'values'))]
        result['full_native_validation'] = all(x['status'] == 'equivalent'
            for k in ('native_source_projection', 'native_vs_cpu') for x in result[k])
    (root / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('lanes', 'stage_bijections')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    main(parser.parse_args().root)
