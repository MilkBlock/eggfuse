"""One batched proposal pool from executions of the installed shared catalog.

Matched births and available inputs are opportunity counts, never saved work.
Each target's compiler must still prove the selected local transitions.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path
from pool import pool, canonical


def maximal(fragments):
    return [f for f in fragments if not any(f['root'] == g['root'] and
            len(f['hops']) < len(g['hops']) and g['hops'][:len(f['hops'])] == f['hops']
            for g in fragments)]


def select(seed, records, budget):
    selected = {canonical(f): f for f in seed}
    groups = set()
    chosen = []
    ranked = sorted(records, key=lambda r: (-Fraction(r['observed']['available_shared_inputs'],
                                                      max(1, r['static_instruction_handles'])),
                                            canonical(r['fragment'])))
    for row in ranked:
        f = row['fragment']
        if row['observed']['matched_births'] < 2 or row['observed']['available_shared_inputs'] == 0:
            continue
        if not f['hops'] or len(f['hops']) >= 16 or canonical(f) in selected:
            continue
        # Alternatives for one source history and receiver overlap. Do not sum
        # them or pay for all anchor choices in this finite selection.
        group = canonical({'root': f['root'], 'hops': f['hops'][:-1], 'rule': f['hops'][-1]['rule']})
        if group in groups:
            continue
        if len(chosen) == budget:
            break
        groups.add(group)
        selected[canonical(f)] = f
        chosen.append(row)
    result = maximal(list(selected.values()))
    assert all(any(f['root'] == g['root'] and g['hops'][:len(f['hops'])] == f['hops']
                   for g in result) for f in seed)
    return result, chosen


def prepare(root, budgets=(64, 256)):
    if not budgets or any(not isinstance(b, int) or not 1 <= b <= 4096 for b in budgets):
        raise ValueError("proposal budgets must be in 1..4096")
    names = [c['case'] for c in json.loads((root/'manifest.json').read_text())['cases']]
    samples, installed = [], {}
    for name in names:
        directory = root/name
        interface = json.loads((directory/'interface.json').read_text())
        observation = json.loads((directory/'catalog-observation.json').read_text())
        program = json.loads((directory/'candidate.json').read_text())
        trace = observation['catalog_trace']
        if (observation['all_saved_run_checks_equal'] is not True or
                observation['source_program'] != program['sha256'] or
                trace['catalog_sha256'] != program['sha256'] or
                trace['schema'] != 'eggfuse-ownership-catalog-trace/v1' or
                len(observation['run_checks']) != observation['runs']):
            raise ValueError(f'{name}: audited installed-catalog observation required')
        records = [{'fragment': r['fragment'], 'static_instruction_handles': r['static_instruction_handles'],
                    'observed': {k: r[k] for k in ('matched_births', 'available_shared_inputs')}}
                   for r in trace['records']]
        samples.append((name, interface, {'schema': 'eggfuse-passive-batch/v1', 'source': trace['source'],
                                         'records': records}))
        installed[name] = {'sha256': program['sha256'], 'selection': program['ownership_fragments']}
    merged, projected, summary = pool(samples, ('matched_births', 'available_shared_inputs'))
    roots = {p: n for n, p in enumerate(sorted({canonical(p) for _, i, _ in samples for p in i['programs']}))}
    rules = {p: n for n, p in enumerate(sorted({canonical(p) for _, i, _ in samples for p in i['rules']}))}
    seeds, local_maps = {}, {}
    for name, interface, _ in samples:
        mapping = {canonical(r['canonical_fragment']): r['fragment'] for r in projected[name]['records']}
        seed = []
        for f in installed[name]['selection']['fragments']:
            portable = {'root': roots[canonical(interface['programs'][f['root']])], 'hops': []}
            for h in f['hops']:
                portable['hops'].append(dict(h, rule=rules[canonical(interface['rules'][h['rule']])],
                                              entry=interface['entries'][h['rule']][h['entry']]))
            mapping[canonical(portable)] = f
            seed.append(portable)
        seeds[name] = seed
        local_maps[name] = mapping
    if any({canonical(f) for f in seeds[n]} != {canonical(f) for f in seeds[names[0]]} for n in names):
        raise ValueError('installed shared seed catalogs differ')
    portable = set.intersection(*(set(m) for m in local_maps.values()))
    rows = [r for r in merged['records'] if canonical(r['fragment']) in portable]
    out = root/'passive'; out.mkdir(exist_ok=True)
    (out/'pooled-observations.json').write_text(json.dumps(merged, separators=(',', ':')))
    variants = []
    for budget in budgets:
        fragments, chosen = select(seeds[names[0]], rows, budget)
        if len(fragments) > 4096:
            raise ValueError('selection exceeds finite catalog bound')
        variant = out/f'budget{budget}'; variant.mkdir(exist_ok=True)
        for name in names:
            directory = variant/name; directory.mkdir(exist_ok=True)
            selection = dict(installed[name]['selection'], max_frames=16, max_fragments=4096,
                             fragments=[local_maps[name][canonical(f)] for f in fragments],
                             ranking={'rule': 'available shared inputs per static handle', 'alternatives_overlap': True,
                                      'performance_admission': 'unvalidated passive proposal ranking'},
                             selection_provenance={'scope': 'batched passive proposals, not measured savings',
                                                   'seed_catalog': installed[name]['sha256'],
                                                   'added_paths': len(chosen)})
            (directory/'selection.json').write_text(json.dumps({'source_program': installed[name]['sha256'],
                                                                'selection': selection}, separators=(',', ':')))
        variants.append({'budget': budget, 'added_paths': len(chosen), 'maximal_paths': len(fragments),
                         'chosen': chosen})
    summary.update(variants=variants, portable_proposals=len(rows), seed_paths=len(seeds[names[0]]),
                   scope='batched proposals from the installed catalog, not actual savings')
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    s = prepare(Path(sys.argv[1]), tuple(map(int, sys.argv[2:])) or (64, 256))
    print(json.dumps({k: v for k, v in s.items() if k != 'variants'}))
    print([(v['budget'], v['added_paths'], v['maximal_paths']) for v in s['variants']])
