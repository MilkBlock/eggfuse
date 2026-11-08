#!/usr/bin/env python3
"""Retain evidence for the field representation step, without claiming scoped completion."""
import argparse
import json
from pathlib import Path
import re


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def collect(root, output):
    checks = {}
    for name in ('workspace-tests', 'fields-tests', 'fields-non-sparse-tests'):
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, values)) for values in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(c[1] for c in counts) == 0
        checks[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    minimal = (root / 'minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    checks['no_default_features'] = 'compile check passed'
    write(output / 'fields-validation.json', checks)

    audit = json.loads((root / 'fields-audit/results.json').read_text())
    lanes = audit['cases']['sum-bits']['lanes']
    old, new = lanes['legacy_fields'], lanes['stable_fields']
    assert old['hashes'] == new['hashes']
    assert new['cell_ownership']['stats']['port_checks'] == 0
    assert new['cell_ownership']['stats']['row_copies'] == 0
    assert new['stable_ports']['live_stable_nodes'] == new['cell_ownership']['stats']['owned_live']
    assert new['stable_ports']['stats']['legacy_key_enqueues'] > 0
    assert new['stable_ports']['stats']['row_views'] > 0
    for k in ('key_completions', 'result_publications', 'owned_live'):
        assert old['cell_ownership']['stats'][k] == new['cell_ownership']['stats'][k]
    write(output / 'fields-audit.json', {
        'scope': 'standalone Cell CPU; frozen sum-bits; field representation only, not a speedup or scoped-wait claim',
        'baseline_revision': '7c7ab5d3',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'],
        'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'canonical_key_maintenance_removed': False,
        'global_wait_removed': False,
        'read_counter_scope': 'accesses since stable fields were enabled up to report capture; includes setup and ordered-audit reads',
        'lanes': {name: {**{k: lane[k] for k in ('args', 'stable_ports', 'stats', 'key_lookup_calls', 'maintenance')},
                         'ownership': lane['cell_ownership']['stats']} for name, lane in lanes.items()},
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
