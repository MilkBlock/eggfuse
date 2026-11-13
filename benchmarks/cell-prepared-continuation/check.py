#!/usr/bin/env python3
"""Charge prepared resumption and retain exact state, Run and effect checks."""
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-continuation/check.py'))


def collect(control, candidate):
    result = base['collect'](control, candidate, control_commit='64f022a8',
        required_extra={'storage-prepared', 'integration-cell_ownership'})
    for case, output in result['workloads'].items():
        a, b = (base['read'](root / f'candidate-{case}/report.json') for root in (control, candidate))
        for label, report in (('control', a), ('candidate', b)):
            scheduler = report['cell_execution']['runtime']['stats']['scheduler']
            for key in ('prepared_resumptions', 'prepared_key_fallbacks', 'completed_without_queue'):
                output['work'][label]['scheduler'][key] = scheduler.get(key, 0)
        keys = ('constructor_prepared_certificates', 'constructor_prepared_sealed',
                'constructor_prepared_fields', 'constructor_prepared_result_reads',
                'rhs_context_suspends', 'rhs_context_resumes', 'rhs_suspend_holds',
                'rhs_suspend_releases')
        output['prepared_and_lifecycle'] = {
            'control': {k: a['stats'][k] for k in keys},
            'candidate': {k: b['stats'][k] for k in keys},
        }
        assert b['stats']['rhs_context_suspends'] == b['stats']['rhs_context_resumes']
        assert b['stats']['rhs_suspend_holds'] == b['stats']['rhs_suspend_releases']
    # Coverage must be observed, rather than inferred from the new code/counters.
    assert result['workloads']['ray']['work']['candidate']['scheduler']['prepared_resumptions'] > 0
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Prepared continuation: exact Runs, states, effects, lifecycle and native sum acceptance passed')
