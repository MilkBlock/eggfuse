"""Summarize actual multi-component match wiring; never score it as a takeover."""
import collections
import hashlib
import json
import pathlib
import sys


def summarize(root):
    source = root / 'multi-source-observation' / 'witness-checked.json'
    raw = source.read_bytes()
    rows = []
    for case in json.loads(raw)['cases']:
        if case['all_saved_run_checks_equal'] is not True:
            raise ValueError('unaudited execution')
        trace = case['catalog_trace']['multi_source']
        if trace['schema'] != 'matched-multi-source/v1' or trace['inconsistent_slots'] or trace['dropped_patterns']:
            raise ValueError('incomplete or inconsistent multi-source observation')
        patterns = trace['patterns']
        counts = {k: trace[k] for k in ('entries', 'multi_component_entries', 'disconnected_entries')}
        counts.update(patterns=len(patterns),
                      connected_applications=sum(p['counts']['applications'] for p in patterns),
                      cross_epoch_applications=sum(p['counts']['cross_epoch_applications'] for p in patterns))
        if counts['connected_applications'] + counts['disconnected_entries'] != counts['multi_component_entries']:
            raise ValueError('unaccounted multi-component Entries')
        memory = json.loads((root / 'rhs-result-control' / case['case'] / 'full-memory.json').read_text())
        if memory['program_sha256'] != case['program'] or memory['final_state_sha256'] != case['final_state']:
            raise ValueError('control census identity mismatch')
        cs = memory['ownership_storage']['components']
        roots = [r for c in cs for r in c['roots'] if r is not None]
        within = sum(len([r for r in c['roots'] if r is not None]) - len({r for r in c['roots'] if r is not None}) for c in cs)
        widths = collections.Counter()
        frames = collections.Counter()
        for p in patterns:
            n = p['counts']['applications']
            widths[len(p['pattern']['components'])] += n
            frames[sum(len(codes) for _, codes in p['pattern']['components'])] += n
        ranked = sorted(patterns, key=lambda p: -p['counts']['applications'])
        rows.append({'case': case['case'], 'program': case['program'], 'runs': case['runs'],
                     'all_saved_run_checks_equal': True, 'counts': counts,
                     'control_final_census': {'components': len(cs), 'bound_signals': len(roots),
                                             'distinct_eq_roots': len(set(roots)), 'duplicate_roots_within_components': within},
                     'component_width_applications': dict(sorted(widths.items())),
                     'source_frame_width_applications': dict(sorted(frames.items())),
                     'top_patterns': ranked[:5]})
    return {'scope': 'standalone Cell CPU observation; matches are not committed mutations or compression savings',
            'input_sha256': hashlib.sha256(raw).hexdigest(),
            'identity_scope': 'query Entry order and static shape/code/operation positions; artifact-local, not canonicalized across workloads',
            'cases': rows}


if __name__ == '__main__':
    pathlib.Path(sys.argv[2]).write_text(json.dumps(summarize(pathlib.Path(sys.argv[1])), indent=2) + '\n')
