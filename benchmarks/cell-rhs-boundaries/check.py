#!/usr/bin/env python3
"""Record Entry maintenance deltas from already validated runtime exports."""
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def run(control, candidate, checks, output):
    validation = read(candidate / 'validation.json')
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == validation['sum']['state_sha256']
    tested = read(checks / 'validation.json')
    assert len(tested) == 8 and all(x['exit_code'] == 0 for x in tested)
    result = dict(scope='actual standalone Cell CPU; work and semantics, not timing',
                  control=read(control / 'manifest.json'), candidate=read(candidate / 'manifest.json'),
                  validation=validation, native_sum_status=proof['status'], checks=tested, workloads={})
    for case in ('sum', 'ray'):
        reports = [read(root / f'candidate-{case}/report.json') for root in (control, candidate)]
        before, after = [r['entry_schedule']['stats'] for r in reports]
        # Maintenance transport must not change the amount of accepted Entry
        # work or which consumer snapshots/epochs are delivered.
        unchanged = ('owner_entry_updates', 'worker_entry_updates', 'predicate_checks',
                     'consumer_seed_deliveries', 'cell_entry_deliveries', 'retired_packets')
        assert all(before[k] == after[k] for k in unchanged)
        result['workloads'][case] = dict(
            unchanged_entry_work={k:after[k] for k in unchanged},
            packet_in_place_updates=after['packet_in_place_updates'],
            packet_epoch_memberships_retained=after['packet_epoch_memberships_retained'],
            row_allocation_reuse={lane:{k:r['entry_schedule']['stats'][k] for k in
                ('row_reuse_checks','row_reuses','row_reuse_shared')} for lane,r in zip(('control','candidate'),reports)},
            phases_diagnostic={lane:{k:sum(s['phases'][k] for s in r['steps'])
                for k in r['steps'][0]['phases']} for lane,r in zip(('control','candidate'),reports)})
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['workloads'], indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
