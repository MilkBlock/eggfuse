#!/usr/bin/env python3
"""Account for runtime storage after a broader, typed passive Bake iteration."""
import json
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def collect(root, batch):
    rows = []
    variant = batch / 'passive/budget4096'
    compiled = {r['case']: r for r in read(variant / 'compiled.json')['cases']}
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        before, after = [read(root / f'{case}-{label}.json') for label in ('seed', 'breadth')]
        checks = read(variant / case / 'witness-checked.json')
        for report, path in ((before, batch / case / 'candidate.json'),
                             (after, variant / case / 'candidate.json')):
            if report['mode'] != 'inherited-owners':
                raise ValueError(f'{case}: storage mode mismatch')
            if report['program_sha256'] != read(path)['sha256']:
                raise ValueError(f'{case}: program mismatch')
            if sum(dict(report['graph_fields']).values()) + report['graph_unlisted_teardown_bytes'] != report['graph_owned_teardown_bytes']:
                raise ValueError(f'{case}: heap accounting')
        if before['final_state_sha256'] != after['final_state_sha256'] or before['runs'] != after['runs']:
            raise ValueError(f'{case}: state/Run mismatch')
        if (checks['all_saved_run_checks_equal'] is not True or checks['runs'] != after['runs']
                or checks['program'] != after['program_sha256'] or checks['final_state'] != after['final_state_sha256']
                or compiled[case]['all_seed_transitions_preserved'] is not True):
            raise ValueError(f'{case}: failed transition/Run proof')
        metrics = {}
        for label, report in (('seed', before), ('breadth', after)):
            components = report['ownership_storage']['components']
            metrics[label] = dict(graph_bytes=report['graph_owned_teardown_bytes'],
                retained_program_bytes=report['retained_program_teardown_bytes'],
                graph_plus_program_bytes=report['graph_owned_teardown_bytes']+report['retained_program_teardown_bytes'],
                execution_peak_bytes=report['execution_and_takeover_peak_bytes'],
                takeover_extra_bytes=report['max_takeover_extra_bytes'],
                components=len(components), frames=sum(len(c['frames']) for c in components),
                source_records=report['source_storage']['completed_owners']['source_records'],
                completed_frames=report['source_storage']['completed_owners']['completed_frames'],
                slot_entries=report['source_storage']['completed_owners']['stored_slot_entries'],
                graph_fields=dict(report['graph_fields']))
        rows.append(dict(case=case, runs=after['runs'], all_saved_run_checks_equal=True,
                         seed_program=before['program_sha256'], program=after['program_sha256'],
                         graph_change_bytes=metrics['breadth']['graph_bytes']-metrics['seed']['graph_bytes'],
                         graph_ratio=metrics['breadth']['graph_bytes']/metrics['seed']['graph_bytes'], **metrics))
    return dict(scope='Same frozen standalone Cell runtime binary; full Graph-owned teardown heap and execution peak; no speed or native acceptance claim',
                binary=read(root / 'binary.json'), cases=rows)


if __name__ == '__main__':
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    for row in result['cases']:
        print(row['case'], row['graph_change_bytes'], row['graph_ratio'])
