#!/usr/bin/env python3
"""Collect the shared port-reader preservation check and frozen process timings.

Uses existing semantic, metric and timing outputs; does not run workloads.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy

REPO = Path(__file__).resolve().parents[2]
TIMING = runpy.run_path(str(REPO / 'benchmarks/raytrace-parallel/collect.py'))
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
            'logical_matches', 'executed_bindings', 'changed')


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    semantics = load(root / 'semantic-acceptance.json')
    assert semantics['status'] == 'pass'
    metrics = [load(root / f'metrics-{lane}.json') for lane in ('baseline', 'candidate')]
    for lane, data in zip(('baseline', 'candidate'), metrics):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
    before, after = [m['metrics'] for m in metrics]
    assert before.keys() == after.keys()
    work = {k: v for k, v in before.items()
            if not any(x in k for x in ('_seconds', '_ns ', '/phases/', 'peak_rss'))}
    assert all(v == after[k] for k, v in work.items())
    cases = {}
    for name, stem, files in (
            ('sum_bits', 'run', ('state.json',)),
            ('port_fixture', 'port', ('state.json', 'stages.json', 'binding-audit.json'))):
        dirs = [root / f'{stem}-{lane}' for lane in ('baseline', 'candidate')]
        a, b = [load(d / 'report.json') for d in dirs]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [
            [s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in ('stats', 'cell_ownership', 'stable_ports'):
            assert a[group] == b[group], (name, group)
        hashes = {file: sha(dirs[0] / file) for file in files}
        assert all(sha(dirs[1] / f) == v for f, v in hashes.items())
        assert b['stable_ports']['stats']['port_reads'] > 0
        cases[name] = {'runs': len(b['steps']), 'ordered_hashes': hashes,
                       'stable_port_stats': b['stable_ports']['stats']}
    tests = {}
    for name, count in (('guards', 2), ('snapshot', 1), ('lifetime', 1)):
        log = root / f'test-{name}.log'
        assert re.search(rf'test result: ok\. {count} passed; 0 failed', log.read_text())
        tests[name] = {'passed': count, 'log_sha256': sha(log)}
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    raw = load(root / 'timing/samples.json')
    assert raw.get('finished_at_utc') and 'failure' not in raw
    timing = {}
    fields = ('inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds',
              'peak_rss_through_inference_bytes')
    for name, lane in raw['lanes'].items():
        assert lane['runtime_sha256'] == sha(root / f'runtime-{name}')
        assert lane['program_file_sha256'] == sha(root / 'sum/program.json')
        assert [r['iteration'] for r in lane['samples']] == list(range(raw['repeat']))
        for row in lane['samples'] + lane['warmup_samples']:
            assert all(row[k] == v for k, v in raw['semantic_reference'].items())
            assert row['allocations'] is None and row['setup_allocations'] is None
        timing[name] = {k: TIMING['distribution']([r[k] for r in lane['samples']]) for k in fields}
        timing[name]['samples'] = [{k: r[k] for k in ('iteration', *fields)} for r in lane['samples']]
    ratios = {name: {k: TIMING['paired_ratio'](
        [r[k] for r in raw['lanes'][name]['samples']],
        [r[k] for r in raw['lanes']['candidate']['samples']]) for k in fields[:-1]}
        for name in ('baseline', 'checkpoint')}
    return {
        'scope': 'standalone Cell CPU; normal release sum-bits; not native egglog timing',
        'commits': {'baseline': '61f272de (same runtime as frozen 05c1fd9a)',
                    'candidate': '24c4ae8a', 'checkpoint': 'ff23dc09'},
        'normal_features': 'sparse-cells,view-ports,storage-metrics',
        'semantic_acceptance': semantics['status'], 'unchanged_work_metrics': len(work),
        'cases': cases, 'tests': tests, 'minimal_features_check': 'pass',
        'binaries': {name: lane['runtime_sha256'] for name, lane in raw['lanes'].items()},
        'program_file_sha256': sha(root / 'sum/program.json'),
        'repeat': raw['repeat'], 'warmups': raw['warmups'],
        'timing': timing, 'candidate_to_reference_ratios': ratios,
        'limits': ['Both inference and process paired intervals include parity for both references; no demonstrated speedup.',
                   'Checkpoint is the previous timed Cell rewrite, not a historical-fastest claim.',
                   'Short sum-bits only; no Raytrace timing or new allocation audit.',
                   'Strict state/Run equality supplements, rather than replaces, semantic acceptance.'],
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    if not __debug__:
        raise SystemExit('run without -O; assertions are verification checks')
    args.output.write_text(json.dumps(collect(args.root), indent=2, ensure_ascii=False) + '\n')
