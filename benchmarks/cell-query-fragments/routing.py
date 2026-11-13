#!/usr/bin/env python3
"""Classify remaining coordinator result work using unchanged accepted programs."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()

def run(accepted, target, output, accepted_commit):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None and lease['kind'] == 'compute'
    assert not git('status', '--porcelain')
    commit = git('rev-parse', 'HEAD')
    output.mkdir(parents=True)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    build = freeze(ROOT, target, output / 'runtime', output / 'build.log',
                   'cell-absorption,view-ports,parallel-publication')
    reference(accepted, output / 'candidate', output / 'runtime', accepted, accepted_commit)
    result = dict(scope='actual standalone Cell CPU; result routing work audit, not timing or a takeover',
                  commit=commit, accepted_commit=accepted_commit, build=build, workloads={})
    keys = ('result_coordinator_rows', 'result_point_rows', 'result_mixed_rule_rows',
            'result_small_rule_rows', 'result_inline_rows', 'result_fragment_rows',
            'result_fragment_batches', 'result_fragment_spans', 'entry_range_batches',
            'range_answer_span_bytes', 'range_answer_span_heap_bytes')
    for case in ('sum', 'ray'):
        report = json.loads((output / 'candidate' / f'candidate-{case}/report.json').read_text())
        stats = report['query_workers']['stats']
        assert sum(stats[k] for k in keys[1:5]) == stats[keys[0]]
        assert report['stage_spine']['direct_changed_roots'] is False
        result['workloads'][case] = {k: stats[k] for k in keys}
    assert git('rev-parse', 'HEAD') == commit and not git('status', '--porcelain')
    (output / 'routing.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['workloads'], indent=2), flush=True)

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--accepted-commit', required=True)
    run(**{k: v.resolve() if isinstance(v, Path) else v
           for k, v in vars(p.parse_args()).items()})
