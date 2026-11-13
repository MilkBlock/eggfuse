#!/usr/bin/env python3
"""Run through the shared compute queue. Compare an unchanged witness catalog."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def run(root, output):
    env = dict(os.environ, CARGO_INCREMENTAL='0')
    subprocess.run(['cargo', 'build', '--locked', '-p', 'eggfuse-cell-compiler', '--features',
        'iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit',
        '--example', 'batch_cell_learning'], check=True, env=env)
    binary = root / 'grouped-selection' / 'batch-frozen'
    binary.parent.mkdir(parents=True, exist_ok=True)
    target = Path(env.get('CARGO_TARGET_DIR', 'target'))
    shutil.copy2(target / 'debug/examples/batch_cell_learning', binary)
    baseline = read(root / 'prefix-all' / 'checked.json')
    for case in baseline['cases']:
        source, dest = root / 'prefix-all' / case['case'], binary.parent / case['case']
        dest.mkdir(parents=True, exist_ok=True)
        for name in ('candidate.json', 'selection.json'):
            shutil.copyfile(source / name, dest / name)
    subprocess.run([str(binary.resolve()), 'check-passive', str(root), 'grouped-selection'], check=True)
    collect(root, output)


def collect(root, output):
    binary = root / 'grouped-selection' / 'batch-frozen'
    baseline = read(root / 'prefix-all' / 'checked.json')
    candidate = {r['case']: r for r in read(binary.parent / 'checked.json')['cases']}
    rows = []
    for old in baseline['cases']:
        new = candidate[old['case']]
        for key in ('program', 'runs', 'final_state', 'all_saved_run_checks_equal', 'key_lookup_calls'):
            if old[key] != new[key]:
                raise ValueError(f'{old["case"]}: changed {key}')
        if new['all_saved_run_checks_equal'] is not True:
            raise ValueError('unvalidated Run checks')
        a, b = old['runtime_stats'], new['runtime_stats']
        for key, value in a.items():
            if key != 'constructor_cell_route_probes' and b.get(key) != value:
                raise ValueError(f'{old["case"]}: changed existing runtime work {key}')
        for key in ('constructor_cell_route_accepted', 'constructor_cell_route_alternative_checks',
                    'constructor_cell_route_alternative_fields', 'constructor_cell_route_key_proved',
                    'constructor_cell_route_compared_admissions'):
            if a[key] != b[key]:
                raise ValueError(f'{old["case"]}: changed candidate admission work {key}')
        if b['constructor_cell_route_anchor_reads'] != a['constructor_cell_route_probes']:
            raise ValueError('changed anchor work')
        saved = a['constructor_cell_route_probes'] - b['constructor_cell_route_probes']
        if saved != b['constructor_cell_route_selection_reuses']:
            raise ValueError('selection accounting')
        rows.append(dict(case=old['case'], program=new['program'], runs=new['runs'],
            all_saved_run_checks_equal=True, other_existing_runtime_counters_equal=True, final_state=new['final_state'],
            key_lookup_calls=new['key_lookup_calls'], route_accepted=b['constructor_cell_route_accepted'],
            anchor_reads=b['constructor_cell_route_anchor_reads'],
            old_dispatch_searches=a['constructor_cell_route_probes'],
            new_dispatch_searches=b['constructor_cell_route_probes'],
            dispatch_searches_saved=saved,
            operation_index_checks=b['constructor_cell_route_operation_checks'],
            alternative_fields=b['constructor_cell_route_alternative_fields']))
    result = dict(scope='Same catalog and saved standalone Run checks; no timing or complete memory claim',
        candidate_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        baseline_report_sha256=hashlib.sha256((root / 'prefix-all' / 'checked.json').read_bytes()).hexdigest(),
        cases=rows)
    output.write_text(json.dumps(result, indent=2) + '\n')
    for row in rows:
        print(row['case'], row['dispatch_searches_saved'], row['operation_index_checks'])


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[3] == '--collect-only':
        collect(Path(sys.argv[1]), Path(sys.argv[2]))
    elif len(sys.argv) == 3:
        run(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        raise SystemExit('grouped_selection.py ROOT OUTPUT [--collect-only]')
