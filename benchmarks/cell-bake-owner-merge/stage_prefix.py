#!/usr/bin/env python3
"""Measure source-prefix stage completion against saved same-catalog runtime."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')
FEATURES = 'iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit'

def read(p):
    return json.loads(p.read_text())

def run(root, control, output, result, reuse=False):
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CARGO_INCREMENTAL='0')
    patch = subprocess.check_output(['git', 'diff', 'HEAD', '--', 'engine', 'tools/cell-compiler'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if reuse:
        if (output / 'source.patch').read_bytes() != patch:
            raise ValueError('source differs from frozen run')
    else:
        (output / 'source.patch').write_bytes(patch)
        subprocess.run(['cargo', 'clean', '-p', 'eggfuse-cell-runtime', '-p', 'eggfuse-cell-compiler', '-p', 'eggfuse-bake'], check=True, env=env)
        subprocess.run(['cargo', 'build', '--locked', '-p', 'eggfuse-cell-compiler', '--features', FEATURES,
                        '--example', 'runtime_storage_peak', '--example', 'batch_cell_learning'], check=True, env=env)
        if subprocess.check_output(['git', 'diff', revision, '--', 'engine', 'tools/cell-compiler']) != patch:
            raise ValueError('source changed during build')
        for name in ('runtime_storage_peak', 'batch_cell_learning'):
            shutil.copy2(Path(env.get('CARGO_TARGET_DIR', 'target')) / 'debug/examples' / name, output / name)
        variant = 'stage-prefix'
        for case in CASES:
            dest = root / variant / case
            dest.mkdir(parents=True, exist_ok=True)
            for name in ('candidate.json', 'selection.json'):
                shutil.copyfile(root / 'prefix-all' / case / name, dest / name)
        subprocess.run([str(output / 'batch_cell_learning'), 'check-passive', str(root), variant], check=True)
    variant = 'stage-prefix'
    checked = {r['case']: r for r in read(root / variant / 'checked.json')['cases']}
    controls = {r['case']: r for r in read(root / 'shared-membership' / 'checked.json')['cases']}
    rows = []
    for case in CASES:
        path = output / f'{case}.json'
        if reuse != 'collect':
            subprocess.run([str(output / 'runtime_storage_peak'), str(root / variant / case / 'candidate.json'),
                            str(path), 'inherited-owners', '--port-domains-only'], check=True)
        old, new = read(control / f'{case}.json'), read(path)
        for key in ('program_sha256', 'runs', 'final_state_sha256', 'mode'):
            if old[key] != new[key]:
                raise ValueError(f'{case}: changed {key}')
        proof = checked[case]
        before_proof = controls[case]
        if before_proof['final_state'] != old['final_state_sha256'] or before_proof['program'] != old['program_sha256']:
            raise ValueError('lookup control differs from memory control')
        # check-passive emits its report only after the terminal check succeeds
        # (batch_cell_learning.rs); that mode omits a separate terminal flag.
        if not (proof['all_saved_run_checks_equal'] is True and proof['runs'] == new['runs']
                and proof['program'] == new['program_sha256']
                and proof['final_state'] == new['final_state_sha256']):
            raise ValueError('Run or terminal validation failed')
        before, after = old['completion_work'], new['completion_work']
        changes = {key: [before.get(key,0), value] for key,value in after.items() if before.get(key,0) != value}
        profile = new['source_storage']['completed_owners']
        if 'constructor_cell_prefix_route_accepted' not in new['completion_work']:
            raise ValueError('stale runtime')
        rows.append(dict(case=case, runs=new['runs'], final_state=new['final_state_sha256'],
            key_lookups_before=before_proof['key_lookup_calls'], key_lookups_after=proof['key_lookup_calls'],
            all_saved_run_checks_equal=True, terminal_check_equal=True, work_changes=changes, prefix_route_accepted=new['completion_work']['constructor_cell_prefix_route_accepted'],
            control_sha256=hashlib.sha256((control / f'{case}.json').read_bytes()).hexdigest(),
            candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            graph_before=old['graph_owned_teardown_bytes'], graph_after=new['graph_owned_teardown_bytes'],
            program_before=old['retained_program_teardown_bytes'], program_after=new['retained_program_teardown_bytes'],
            peak_before=old['execution_and_takeover_peak_bytes'], peak_after=new['execution_and_takeover_peak_bytes'],
            membership=profile))
    result.write_text(json.dumps(dict(scope='Standalone Cell CPU requested heap and exact saved Run checks; not timing or native acceptance',
        revision=revision, patch_sha256=hashlib.sha256(patch).hexdigest(),
        runtime_sha256=hashlib.sha256((output / 'runtime_storage_peak').read_bytes()).hexdigest(),
        check_binary_sha256=hashlib.sha256((output / 'batch_cell_learning').read_bytes()).hexdigest(),
        checked_report_sha256=hashlib.sha256((root / variant / 'checked.json').read_bytes()).hexdigest(), cases=rows), indent=2)+'\n')
    for row in rows:
        print(row['case'], row['graph_before'], row['graph_after'], row['prefix_route_accepted'], row['work_changes'].get('rhs_frames_avoided'))

if __name__ == '__main__':
    reuse = 'collect' if '--collect-only' in sys.argv else '--reuse-frozen' in sys.argv
    run(*(Path(a).resolve() for a in sys.argv[1:] if a not in ('--reuse-frozen','--collect-only')), reuse=reuse)
