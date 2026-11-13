"""Audit compiled relocation maps against saved source Shapes, without execution."""
import collections
import hashlib
import json
import pathlib
import sys


def summarize(root):
    rows = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        path = root / 'multi-source-observation' / name / 'compiled-joins.json'
        raw = path.read_bytes()
        data = json.loads(raw)
        control = json.loads((root / 'rhs-result-control' / name / 'full-memory.json').read_text())
        if data['source_program'] != control['program_sha256']:
            raise ValueError('source program mismatch')
        shapes = control['ownership_storage']['shapes']
        ranks = collections.Counter()
        uses = 0
        for row in data['candidates']:
            c = row['compiled']
            old = [shapes[i] for i, _ in c['pattern']['components']]
            maps, new = c['symbol_maps'], c['shape']
            offsets = [0, len(old[0]['programs'])]
            assert c['frame_offsets'] == offsets
            assert new['programs'] == old[0]['programs'] + old[1]['programs']
            assert c['aliased_symbols'] == sum(len(s['signals']) for s in old) - len(new['signals'])
            expected = [set() for _ in new['signals']]
            for component, source in enumerate(old):
                assert len(maps[component]) == len(source['signals'])
                for frame, ports in enumerate(source['ports']):
                    assert new['ports'][offsets[component] + frame] == [maps[component][s] for s in ports]
                for symbol, steps in enumerate(source['signals']):
                    expected[maps[component][symbol]].update((offsets[component] + step['frame'], step['op']) for step in steps)
            for actual, wanted in zip(new['signals'], expected):
                assert [(s['frame'], s['op']) for s in actual] == sorted(wanted)
            ranks[c['aliased_symbols']] += 1
            uses += row['observed']['applications']
        rows.append({'case': name, 'source_program': data['source_program'],
                     'compiled_sha256': hashlib.sha256(raw).hexdigest(),
                     'candidates': len(data['candidates']), 'observed_applications': uses,
                     'aliased_symbols_per_candidate': dict(sorted(ranks.items())),
                     'unsupported_wider_patterns': data['unsupported_wider_patterns'],
                     'over_frame_bound_patterns': data['over_frame_bound_patterns'],
                     'all_source_wiring_preserved': True})
    return {'scope': 'offline typed candidate compilation and static relocation audit; no runtime takeover, memory saving or RHS speedup', 'cases': rows}


if __name__ == '__main__':
    pathlib.Path(sys.argv[2]).write_text(json.dumps(summarize(pathlib.Path(sys.argv[1])), indent=2) + '\n')
