#!/usr/bin/env python3
"""Validate and account for singleton admission using a same-binary control."""
import json
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def collect(root, batch):
    checks = {r['case']: r for r in read(batch / 'singleton-audit/checked.json')['cases']}
    rows = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        a, b = [read(root / f'{case}-{mode}.json') for mode in ('multi', 'singleton')]
        program = read(batch / case / 'candidate.json')['sha256']
        check = checks[case]
        if (check['all_saved_run_checks_equal'] is not True or check['program'] != program
                or check['runs'] != b['runs'] or check['final_state'] != b['final_state_sha256']):
            raise ValueError(f'{case}: Run validation mismatch')
        if a['mode'] != 'multi-owner-control' or b['mode'] != 'inherited-owners':
            raise ValueError(f'{case}: mode mismatch')
        for field in ('program_sha256', 'runs', 'final_state_sha256', 'retained_program_teardown_bytes'):
            if a[field] != b[field]:
                raise ValueError(f'{case}: changed {field}')
        if b['program_sha256'] != program:
            raise ValueError(f'{case}: wrong input')
        metrics = {}
        for label, report in (('control', a), ('singleton', b)):
            fields = dict(report['graph_fields'])
            if sum(fields.values()) + report['graph_unlisted_teardown_bytes'] != report['graph_owned_teardown_bytes']:
                raise ValueError(f'{case}: heap accounting')
            source = report['source_storage']
            owner = source['completed_owners']
            metrics[label] = dict(graph_bytes=report['graph_owned_teardown_bytes'],
                program_bytes=report['retained_program_teardown_bytes'],
                execution_peak_bytes=report['execution_and_takeover_peak_bytes'],
                takeover_extra_bytes=report['max_takeover_extra_bytes'],
                source_records=owner['source_records'], completed_frames=owner['completed_frames'],
                owners=owner['owners'], inherited_lifecycles=owner['inherited_fact_lifecycles'],
                fact_capacity_bytes=source['fact_record_capacity_bytes'],
                fact_live_bytes=source['fact_record_live_bytes'],
                owner_records_bytes=source['completed_owner_records_bytes'],
                restoration=owner['restoration'], graph_fields=fields)
        rows.append(dict(case=case, program=program, runs=b['runs'], all_saved_run_checks_equal=True,
            graph_bytes_saved=a['graph_owned_teardown_bytes']-b['graph_owned_teardown_bytes'],
            graph_ratio=b['graph_owned_teardown_bytes']/a['graph_owned_teardown_bytes'], **metrics))
    return dict(scope='Actual standalone Cell CPU; same-binary singleton admission ablation; no timing/native proof claim',
                binary=read(root / 'binary.json'), cases=rows)


if __name__ == '__main__':
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    for row in result['cases']:
        print(row['case'], row['graph_bytes_saved'], row['graph_ratio'])
