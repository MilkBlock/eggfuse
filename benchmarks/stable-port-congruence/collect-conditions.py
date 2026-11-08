#!/usr/bin/env python3
"""Account for closed local conditions and the boundary proof that permits them."""
import argparse
import json
from pathlib import Path
import re


def collect(root, output):
    validation = {}
    for name in ('local-condition-workspace-tests', 'local-condition-tests', 'local-condition-non-sparse-tests'):
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    minimal = (root / 'local-condition-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    (output / 'local-condition-validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    audit = json.loads((root / 'local-condition-audit/results.json').read_text())
    lanes = audit['cases']['sum-bits']['lanes']
    old, new = lanes['port_keys'], lanes['local_conditions']
    assert old['hashes'] == new['hashes']
    port = new['stable_ports']['stats']
    local = new['stable_ports']['local_conditions']['stats']
    assert port['equality_completions'] == old['stable_ports']['stats']['equality_completions']
    assert local['attempts'] == port['equality_completions']
    assert local['attempts'] == sum(local[k] for k in ('closed_regions', 'open_fallbacks', 'uncovered_shapes'))
    assert port['key_lookups'] + local['closed_regions'] == old['stable_ports']['stats']['key_lookups']
    for lane in lanes.values():
        assert lane['stats']['repair_key_hash_changes'] == 0
        assert lane['maintenance']['stats']['repair_key_probes'] == 0
        assert lane['stable_ports']['pending_port_equality_checks'] == 0
    result = {
        'scope': 'standalone Cell CPU; exact ordered audit; no latency or parallel-execution claim',
        'baseline_revision': 'f8a3ee35',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'global_wait_removed': False,
        'condition_state': 'shared static wiring; live facts and current ports checked at each visit; no per-instance condition subscriptions',
        'counter_scope': 'accesses since mode activation, including setup and audit reads',
        'lanes': {name: {**{k: lane[k] for k in ('args', 'stable_ports', 'stats', 'maintenance', 'key_lookup_calls')},
                         'ownership': lane['cell_ownership']['stats']} for name, lane in lanes.items()},
    }
    (output / 'local-condition-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
