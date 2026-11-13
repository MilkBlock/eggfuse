#!/usr/bin/env python3
"""Complete heap comparison for unchanged catalogs; use the shared compute queue."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')


def read(path):
    return json.loads(path.read_text())


def collect(output, result):
    rows = []
    for case in CASES:
        old, new = [read(output / f'{case}-{label}.json') for label in ('control', 'candidate')]
        for key in ('program_sha256', 'runs', 'final_state_sha256', 'mode'):
            if old[key] != new[key]:
                raise ValueError(f'{case}: {key} changed')
        metrics = {}
        for label, report in [('control', old), ('candidate', new)]:
            graph, program = dict(report['graph_fields']), dict(report['program_fields'])
            if sum(graph.values()) + report['graph_unlisted_teardown_bytes'] != report['graph_owned_teardown_bytes']:
                raise ValueError('Graph accounting')
            if sum(program.values()) != report['retained_program_teardown_bytes']:
                raise ValueError('Program accounting')
            metrics[label] = dict(graph_bytes=report['graph_owned_teardown_bytes'],
                program_bytes=report['retained_program_teardown_bytes'],
                witness_plan_bytes=program['ownership.witnesses'],
                execution_peak_bytes=report['execution_and_takeover_peak_bytes'])
        deltas = {}
        for category in ('graph_fields', 'program_fields'):
            before, after = dict(old[category]), dict(new[category])
            deltas[category] = {key: after.get(key, 0) - before.get(key, 0)
                for key in sorted(before.keys() | after.keys())
                if after.get(key, 0) != before.get(key, 0)}
        rows.append(dict(case=case, program=old['program_sha256'], runs=old['runs'],
            final_state=old['final_state_sha256'], field_deltas=deltas, **metrics))
    result.write_text(json.dumps(dict(scope='Standalone Cell CPU requested heap; same artifacts, two frozen runtimes; no timing claim',
        builds=read(output / 'builds.json'), cases=rows), indent=2) + '\n')
    for row in rows:
        print(row['case'], row['control'], row['candidate'])


def run(control, root, output, result):
    current = Path.cwd()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CARGO_INCREMENTAL='0', CARGO_TARGET_DIR=str(current / 'target'))
    builds = {}
    expected = {label: {r['case']: r for r in read(root / variant / 'checked.json')['cases']}
                for label, variant in [('control', 'prefix-all'), ('candidate', 'grouped-selection')]}
    for label, source in [('control', control), ('candidate', current)]:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        guard = ['git', 'diff', '--exit-code', commit, '--', 'engine', 'tools/cell-compiler/src',
                 'tools/cell-compiler/examples/runtime_storage_peak.rs']
        subprocess.run(guard, cwd=source, check=True)
        # Local package artifacts in a shared target can collide across worktrees.
        # Drop workspace package outputs, retaining third-party dependency caches.
        subprocess.run(['cargo', 'clean', '-p', 'eggfuse-cell-runtime', '-p',
            'eggfuse-cell-compiler', '-p', 'eggfuse-bake'], cwd=source, env=env, check=True)
        subprocess.run(['cargo', 'build', '--locked', '-p', 'eggfuse-cell-compiler', '--features',
            'iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit',
            '--example', 'runtime_storage_peak'], cwd=source, env=env, check=True)
        subprocess.run(guard, cwd=source, check=True)
        binary = output / f'{label}-frozen'
        shutil.copy2(current / 'target/debug/examples/runtime_storage_peak', binary)
        builds[label] = dict(commit=commit,
                            binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
        for case in CASES:
            subprocess.run([str(binary.resolve()), str(root / 'prefix-all' / case / 'candidate.json'),
                str(output / f'{case}-{label}.json'), 'inherited-owners', '--port-domains-only'], check=True)
            work = read(output / f'{case}-{label}.json')['completion_work']
            if (label == 'candidate') != ('constructor_cell_route_selection_reuses' in work):
                raise ValueError('runtime build does not match the expected dispatch implementation')
            saved = expected[label][case]
            actual = read(output / f'{case}-{label}.json')
            if (saved['all_saved_run_checks_equal'] is not True or actual['program_sha256'] != saved['program']
                    or actual['final_state_sha256'] != saved['final_state'] or actual['runs'] != saved['runs']):
                raise ValueError('memory run does not match audited source execution')
            for key in ('constructor_cell_route_probes', 'constructor_cell_route_accepted',
                        'constructor_cell_route_selection_reuses'):
                if work.get(key) != saved['runtime_stats'].get(key):
                    raise ValueError(f'runtime work differs from frozen implementation: {key}')
    (output / 'builds.json').write_text(json.dumps(builds, indent=2) + '\n')
    collect(output, result)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--collect-only':
        collect(Path(sys.argv[2]).resolve(), Path(sys.argv[3]))
    elif len(sys.argv) == 5:
        run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), Path(sys.argv[4]))
    else:
        raise SystemExit('usage: dispatch_storage.py CONTROL ROOT OUTPUT RESULT | --collect-only OUTPUT RESULT')
