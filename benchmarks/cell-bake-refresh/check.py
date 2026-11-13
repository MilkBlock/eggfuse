#!/usr/bin/env python3
"""Retain the parallel semantic gate and separately verify incoming Bake fixtures."""
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-continuation/check.py'))
read, sha = base['read'], base['sha']


def collect(control, candidate):
    result = base['collect'](control, candidate, control_commit='7a9e2f41', required_extra={
        'integration-cell_ownership', 'integration-unit_fact_specialization',
        'integration-ownership_receipts', 'pooling', 'batch-examples', 'batch-verify',
    })
    result['merged_branch'] = 'codex/cell-structural-compression'
    result['merged_commit'] = 'e992797be4ebbef00bb34f6188d3bef3ac0802e3'
    attempts = candidate / 'validation-attempts.json'
    result['validation_attempts'] = read(attempts) if attempts.exists() else []
    for case, work in result['workloads'].items():
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        work['graph_stat_changes'] = {
            key: {'control': a['stats'].get(key), 'candidate': value}
            for key, value in b['stats'].items() if a['stats'].get(key) != value
        }
    batch = candidate / 'batch'
    frozen = read(batch / 'frozen-inputs.json')
    for row in frozen['inputs']:
        assert sha(batch / row['file']) == row['sha256']
    manifest = read(batch / 'manifest.json')
    reports = read(batch / 'verification.json')['cases']
    assert {r['case'] for r in reports} == {r['case'] for r in manifest['cases']}
    for original, actual in zip(manifest['cases'], reports):
        assert original['case'] == actual['case']
        assert original['runs'] == actual['runs']
        assert original['final_state'] == actual['final_state']
        assert actual['run_graph_rhs_writes_equal'] is True
        for lane in ('baseline', 'candidate'):
            assert read(batch / actual['case'] / f'{lane}.json')['sha256'] == actual[lane]
    result['incoming_batch_regression'] = {'frozen': frozen, 'cases': reports,
        'scope': 'source Run graph, ordered RHS and physical writes; no native contract extension'}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Bake merge: parallel state/Run/effect checks, incoming batch and native sum acceptance passed')
