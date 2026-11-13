"""Locate runtime storage obligations before admitting a saturated Cell takeover.

Static sites are compared with final live identities, never with root equality.
An unused local site is not proof its exported slot or boundary may be removed.
"""
import collections
import json
import sys
from pathlib import Path


def classify(storage, frames):
    facts = {(f['cell'], s['op']): s for f in frames for s in f['facts']}
    live_frames = {f['cell'] for f in frames}
    positioned = set()
    counts = collections.Counter()
    for component in storage['components']:
        shape = storage['shapes'][component['shape']]
        counts['components'] += 1
        counts['source_frames'] += len(component['frames'])
        for cell in component['frames']:
            if cell in positioned:
                raise ValueError('Cell has multiple live composition positions')
            positioned.add(cell)
            counts['composition_positions_without_source_frame'] += cell not in live_frames
        counts['multi_frame_components'] += len(component['frames']) > 1
        for symbol, value in enumerate(component['signals']):
            if value is None:
                continue
            counts['bound_symbols'] += 1
            sites = shape['signals'][symbol]
            live = []
            for site in sites:
                fact = facts.get((component['frames'][site['frame']], site['op']))
                counts['static_dispatch_sites'] += 1
                if fact is not None and fact['owned']:
                    counts['live_owned_dispatch_sites'] += 1
                    live.append(fact)
                else:
                    counts['absent_or_unowned_dispatch_sites'] += 1
            counts['symbols_without_live_owned_site'] += not live
            counts['symbols_with_only_hidden_owned_sites'] += bool(live) and all(f['hidden'] for f in live)
    return dict(counts)


def analyze(root):
    cases = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        d = root / name
        heap = json.loads((d / 'candidate-atomic-heap.json').read_text())
        observation = json.loads((d / 'catalog-observation.json').read_text())
        assert heap['program_sha256'] == observation['source_program']
        assert observation['all_saved_run_checks_equal'] is True
        fields = dict(heap['graph_fields'])
        total = heap['graph_owned_teardown_bytes']
        maintenance = sum(fields[k] for k in ('ownership.components', 'ownership.frames',
                                              'ownership.boundaries', 'stable_ports'))
        saturation = observation['catalog_trace']['saturation']['rows']
        covered = sum(r['counts']['applications'] for r in saturation
                      if r['outcome'] in ('rhs_covered', 'rhs_covered_by_inputs'))
        cases.append(dict(case=name, program=heap['program_sha256'], graph_bytes=total,
            cell_bytes=fields['cells'], maintenance_bytes=maintenance,
            bytes_remaining_if_all_cell_storage_disappeared=total-fields['cells'],
            fully_covered_apply_observations=covered,
            apply_observations=sum(r['counts']['applications'] for r in saturation),
            current_layout=classify(heap['ownership_storage'],
                heap['source_storage']['fact_lifecycle']['frames'])))
    return dict(scope='saved actual standalone Cell runtime; storage and dispatch census, not savings',
        limitations=['coverage observations are from the same source/catalog, not linked to final surviving apply instances',
                     'hidden owned facts still require congruence maintenance',
                     'symbols without local owned sites can still serve external Entry or slot reads',
                     'static site counts are snapshot structure, not measured dispatch visits',
                     'the zero-Cell-storage bound is deliberately unattainable, not a proposed representation'], cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')
