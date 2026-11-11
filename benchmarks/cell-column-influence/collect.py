#!/usr/bin/env python3
"""Validate saved column-influence diagnostics, without running workloads."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signature(report):
    rows = [{k:v for k,v in step.items() if k not in ('elapsed_seconds','phases')}
            for step in report['steps']]
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def collect(root, output):
    preceding = read(Path(__file__).resolve().parent.parent / 'cell-entry-reverse/results.json')
    control_binary = root.parent / 'cell-entry-reverse/runtime-final'
    assert sha(control_binary) == preceding['binary_sha256']
    result = {'baseline_commit':'50316626',
              'scope':'standalone Cell CPU work and relative correctness; no throughput result',
              'binary_sha256':[sha(control_binary),sha(root/'runtime-grouped')], 'cases':{}}
    for case in ('sum','ray1280','ray-full'):
        before = root/'ray-control' if case=='ray-full' else root.parent/'cell-entry-reverse'/(case+'-final-off')
        after = root/(case+'-grouped')
        if case != 'ray-full':
            assert sha(before/'report.json') == preceding['cases'][case]['reports_sha256'][0]
        a,b = [read(p/'report.json') for p in (before,after)]
        assert sha(before/'state.json') == sha(after/'state.json')
        assert signature(a) == signature(b)
        for key in ('stats','indexed_columns','entry_schedule','free_join','key_lookup_calls',
                    'prefix_configuration','program_sha256','publication'):
            assert a[key] == b[key], (case,key)
        old,new = [r['sieve'].copy() for r in (a,b)]
        assert new.pop('column_influence') == 'cell-fields/v1'
        groups = new.pop('influence_groups')
        payload = new.pop('influence_payload_bytes')
        work = new['stats'].copy()
        skipped = work.pop('unchanged_column_rows')
        checks = work.pop('column_checks')
        work['update_rows'] += skipped
        new['stats'] = work
        assert old == new, 'support contents, propagation, probes and rejection work must agree'
        result['cases'][case] = {
            'runs':len(b['steps']), 'state_sha256':sha(after/'state.json'),
            'ordered_run_sha256':signature(b),
            'report_sha256':[sha(p/'report.json') for p in (before,after)],
            'summary_update_rows':[a['sieve']['stats']['update_rows'],b['sieve']['stats']['update_rows']],
            'unchanged_column_rows':skipped,
            'column_checks':checks,
            'equal_weight_update_and_check_delta':checks-skipped,
            'added_keys':b['sieve']['stats']['added_keys'],
            'dependency_rows':b['sieve']['stats']['dependency_rows'],
            'compiled_mask_and_group_payload_bytes':payload,
            'compiled_influence_groups':groups,
            'graph_effects_and_ordered_runs_equal':True,
            'all_other_sieve_work_equal':True,
        }
    assert read(root/'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root/'semantic/run-values/state.json') == result['cases']['sum']['state_sha256']
    result['sum_native_acceptance']={'status':'pass','sha256':sha(root/'semantic-acceptance.json')}
    output.write_text(json.dumps(result,indent=2)+'\n')
    for case, data in result['cases'].items():
        print(case, data['summary_update_rows'], 'exact state and ordered Runs')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('validation requires Python assertions; do not use -O')
    collect(Path(sys.argv[1]),Path(sys.argv[2]))
