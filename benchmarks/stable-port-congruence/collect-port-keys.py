#!/usr/bin/env python3
"""Keep exact semantics and replacement-work evidence for immutable key hints."""
import argparse
import json
from pathlib import Path
import re


def collect(root, output):
    validation = {}
    for name in ('port-key-workspace-tests', 'port-key-tests', 'port-key-non-sparse-tests'):
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    minimal = (root / 'port-key-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    (output / 'port-key-validation.json').write_text(json.dumps(validation, indent=2) + '\n')

    audit = json.loads((root / 'port-key-audit-final/results.json').read_text())
    lanes = audit['cases']['sum-bits']['lanes']
    old, new = lanes['stable_fields'], lanes['port_keys']
    assert old['hashes'] == new['hashes']
    assert old['stats']['repair_key_hash_changes'] > 0
    assert new['stats']['repair_key_hash_changes'] == 0
    assert new['maintenance']['stats']['repair_key_probes'] == 0
    assert new['cell_ownership']['stats']['key_completions'] == 0
    ports = new['stable_ports']
    assert ports['pending_canonical_keys'] == ports['pending_port_equality_checks'] == 0
    assert ports['stats']['equality_completions'] == old['cell_ownership']['stats']['key_completions']
    assert ports['stats']['birth_hint_hits'] > 0 and ports['stats']['port_domain_probes'] > 0
    assert ports['stats']['key_field_comparisons'] > 0
    assert ports['birth_indexed_port_keys'] > 0
    result = {
        'scope': 'standalone Cell CPU; frozen sum-bits; exact port keys, no latency or scoped-wait claim',
        'field_step_revision': '4b0541ad',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'canonical_key_maintenance_removed_for_covered_eq_key_constructors': True,
        'immutable_birth_hints_retained': True,
        'global_wait_removed': False,
        'local_static_pair_conditions_implemented': False,
        'counter_scope': 'accesses since mode activation; includes setup and audit reads; not execution-only allocation counts',
        'lanes': {name: {**{k: lane[k] for k in ('args', 'stable_ports', 'stats', 'maintenance', 'key_lookup_calls')},
                         'ownership': lane['cell_ownership']['stats']} for name, lane in lanes.items()},
    }
    initial = root / 'port-key-audit/results.json'
    if initial.exists():
        previous = json.loads(initial.read_text())['cases']['sum-bits']['lanes']['port_keys']
        result['intermediate_no_birth_hint_probe'] = {
            'description': 'exploratory implementation; not the final runtime',
            'same_exact_hashes': previous['hashes'] == new['hashes'],
            'stats': previous['stable_ports']['stats'],
        }
    (output / 'port-key-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    collect(args.root, args.output)
