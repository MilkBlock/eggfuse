#!/usr/bin/env python3
"""Freeze current-branch work/semantic exports before sampling that binary."""
import gzip
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

BENCHMARKS = Path(__file__).resolve().parents[1]


def run(config, output, runtime, accepted, commit):
    jobs = runpy.run_path(str(BENCHMARKS.parent / 'tools/local_jobs.py'))
    if jobs['current_lease']() is None:
        raise RuntimeError('Run this experiment through the shared compute queue')
    runpy.run_path(str(BENCHMARKS / 'cell-worker-runs/run.py'))['run'](
        config, output, runtime, control_commit=commit)
    helpers = runpy.run_path(str(BENCHMARKS / 'cell-bake-full-merge/check.py'))
    read, sha = helpers['read'], helpers['sha']
    keys = runpy.run_path(str(BENCHMARKS / 'raytrace-parallel/measure.py'))['KEYS']
    results = {}
    for case in ('sum', 'ray'):
        before = read(accepted / f'candidate-{case}/report.json')
        after = read(output / f'candidate-{case}/report.json')
        assert before['status'] == after['status'] == 'complete'
        assert before['program_sha256'] == after['program_sha256']
        state = sha(output / f'candidate-{case}/state.json')
        assert state == sha(accepted / f'candidate-{case}/state.json')
        assert [[s[k] for k in keys] for s in before['steps']] == [[s[k] for k in keys] for s in after['steps']]
        effects = ('bindings','constructor_requests','constructor_reused','logical_facts_created',
                   'function_updates','union_requests','unions','merge_calls')
        assert all(before['stats'][k] == after['stats'][k] for k in effects)
        results[case] = dict(exact_state_runs_effects=True, runs=len(after['steps']), state_sha256=state)
    subprocess.run([sys.executable, str(BENCHMARKS / 'marker-handoff/choice_diagnosis.py'),
        str(BENCHMARKS.parent / 'out/cell-entry-owned/semantic'), str(output / 'semantic-acceptance.json')], check=True)
    proof = read(output / 'semantic-acceptance.json')
    assert proof['status'] == 'pass' and proof['input_sha256']['cpu_values'] == results['sum']['state_sha256']
    state = output / 'candidate-ray/state.json'
    with state.open('rb') as source, gzip.open(str(state)+'.gz', 'wb', compresslevel=1) as compressed:
        shutil.copyfileobj(source, compressed)
    state.unlink()
    (output / 'validation.json').write_text(json.dumps(results, indent=2)+'\n')
    print('Frozen current-branch exports match the reviewed state, source Runs and effects')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    run(*(Path(arg).resolve() for arg in sys.argv[1:5]), sys.argv[5])
