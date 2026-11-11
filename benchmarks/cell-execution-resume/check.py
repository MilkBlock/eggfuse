#!/usr/bin/env python3
"""Reuse the full baseline work/Run checker and require real Cell resumption."""
import json
from pathlib import Path
import runpy
import sys


def check(root, prior, output):
    prefix = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cell-execution-prefix/check.py'))
    prefix['check'](root, prior, output)
    result = json.loads(output.read_text())
    result['phase'] = 'owned Cell resumption between source-ordered shared effects'
    result['limits'] += (' Resumption uses exclusive frame borrows; the coordinator '
                         'waits for each frontier. No independent graph-effect scheduling '
                         'or full utilization is established.')
    for case, work in result['workloads'].items():
        report = json.loads((root / case / 'report.json').read_text())
        resume = report['cell_execution']['runtime']
        assert resume['enabled'] and resume['grain'] == 1
        counts = resume['stats']
        assert counts['worker_operations'] > 0
        assert counts['local_operations'] >= counts['worker_operations']
        assert counts['worker_segments'] <= counts['segments']
        assert counts['failures'] == 0
        work['resumption'] = resume
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({c: v['resumption']['stats'] for c, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
