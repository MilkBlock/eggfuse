#!/usr/bin/env python3
"""Retain the scoped graph contract, queue overhead, and conservative coverage limit."""
import argparse
import json
from pathlib import Path
import re


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        name = f'scoped-core-{suffix}'
        log = (root / f'{name}.log').read_text()
        assert 'test result: FAILED' not in log
        counts = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert counts and sum(row[1] for row in counts) == 0
        validation[name] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*counts))))
    log = (root / 'scoped-core-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    (output / 'scoped-core-validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    audit = json.loads((root / 'scoped-core-audit/results.json').read_text())
    lanes = audit['cases']['sum-bits']['lanes']
    old, new = lanes['local_conditions'], lanes['scoped_queues']
    assert old['hashes'] == new['hashes']
    assert old['stats'] == new['stats']
    assert old['stable_ports'] == new['stable_ports']
    scoped = new['scoped_completion']
    assert scoped['enabled'] and scoped['pending_tasks'] == 0
    assert scoped['stats']['scope_requests'] == scoped['stats']['bypassed_tasks'] == 0
    program = json.loads((root / 'sum-program.json').read_text())
    opaque = [{'id':i, 'table':program['recipe']['tables'][i]['name'],
               'schema':program['recipe']['tables'][i]['schema'],
               'merge':program['recipe']['tables'][i].get('merge_expr')}
              for i in scoped['plan']['opaque_tables']]
    result = {
        'scope': 'standalone Cell CPU; scoped Graph API and table queues; Executor still completes every Run globally',
        'baseline_revision': 'd68f334c',
        'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'],
        'hashes': new['hashes'], 'runs': new['runs'],
        'exact_ordered_semantics_match': True,
        'graph_scope_fixtures': ['independent chain remains pending', 'original epoch preserved',
            'transitive cross-sort chain waits', 'mutable merge dependency waits',
            'opaque pending merge retains full completion', 'foreign program scope rejected'],
        'executor_independent_progress_verified': False,
        'global_wait_removed': False,
        'timing_or_parallel_claim': False,
        'scoped_completion': scoped,
        'opaque_table_details': opaque,
        'limitation': 'Type/table reachability admits zero deferrable tables in this workload; concrete Cell ports and precise merge/container effects are required.',
        'new_queue_work_is_overhead_until_scoped_executor_integration': True,
    }
    (output / 'scoped-core-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
