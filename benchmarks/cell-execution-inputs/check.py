#!/usr/bin/env python3
"""Check input-ready preparation against the saved ordered-resumption runtime."""
import json
from pathlib import Path
import runpy
import sys


def check(root, prior, output):
    helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cell-execution-prefix/check.py'))
    helpers['check'](root, prior, output)
    result = json.loads(output.read_text())
    result.update(control_commit='4ed640e2', control_runtime_commit='ed662552', control_tag=None,
                  phase='input-derived scalar preparation in the existing query invocation')
    result['limits'] += (' Later prepared values are consumed only at their source position; '
                         'shared effects remain ordered. No new timing campaign or '
                         'asynchronous parked-frame scheduling is established.')
    for case, work in result['workloads'].items():
        old = helpers['read'](prior / case / 'report.json')
        new = helpers['read'](root / case / 'report.json')
        execution = new['query_workers']['stats']['execution']
        later = execution['later_operations']
        consumed = new['stats']['prepared_rhs_later_operations']
        before = old['cell_execution']['runtime']['stats']
        after = new['cell_execution']['runtime']['stats']
        assert new['cell_execution']['runtime']['grain'] == 1
        assert 0 < consumed <= later
        assert execution['later_deferred_failures'] == after['failures'] == 0
        assert execution['frame_growths'] == 0
        assert after['worker_segments'] < before['worker_segments']
        assert after['local_operations'] + consumed == before['local_operations']
        old_query = old['query_workers']['stats']
        assert execution['operations'] - later == old_query['execution']['operations']
        worker_added = sum(new['query_workers']['stats']['worker_local_operations']) - sum(old_query['worker_local_operations'])
        assert 0 <= worker_added <= later
        # Preparation may touch losing candidates; only source-consumed work
        # is removed from RHS. Existing prefix preparation is a disjoint subset.
        work['total_prepared_results_consumed'] = work.pop('serial_rhs_operations_removed') + consumed
        work['prepared_operations_not_consumed'] -= consumed
        assert work['prepared_operations_not_consumed'] >= 0
        work['later_preparation'] = {
            'prepared': later, 'consumed': consumed, 'not_consumed': later - consumed,
            'worker_prepared': worker_added, 'inline_prepared': later - worker_added,
            'resumption_before': before, 'resumption_after': after,
            'query_preparation_before': old['query_workers']['stats']['execution'],
            'compiled_plan_bytes_added': new['cell_execution']['compiled_payload_bytes']
                - old['cell_execution']['compiled_payload_bytes'],
            'spine_fragment_storage': {k: [old['stage_spine']['stats'][k], new['stage_spine']['stats'][k]]
                for k in ('query_fragment_slots', 'query_fragment_capacity_bytes',
                          'query_fragment_sealed_slots', 'query_fragment_sealed_capacity_bytes')},
        }
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({c: v['later_preparation'] for c, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
