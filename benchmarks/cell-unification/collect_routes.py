#!/usr/bin/env python3
"""Validate saved Cell route checks and summarize one interleaved timing trial."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy

REPO = Path(__file__).resolve().parents[2]
TIMING = runpy.run_path(str(REPO / 'benchmarks/raytrace-parallel/collect.py'))
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')
NEW = {'plan_index_probes', 'source_index_probes', 'local_witness_route_index_probes',
       'local_witness_route_comparisons', 'local_witness_read_index_probes'}


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items()
                if k not in NEW and not k.endswith('_seconds') and
                k not in ('plan_comparisons', 'local_witness_route_steps')}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def collect(root, commit):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    result = {
        'scope': 'standalone Cell CPU; ordinary release; not native egglog timing',
        'features': 'sparse-cells,view-ports,storage-metrics',
        'baseline_commit': '7632423c', 'candidate_commit': commit,
        'semantic_acceptance': 'pass', 'cases': {}, 'tests': {},
        'allocation_status': 'not collected; vector capacity is not total allocation or memory',
    }
    for case in ('sum_bits', 'reused', 'replaced', 'borrowed', 'full'):
        paths = [root / (f'run-{lane}' if case == 'sum_bits' else f'fixtures/{case}-{lane}')
                 for lane in ('baseline', 'candidate')]
        program = root / ('sum/program.json' if case == 'sum_bits' else f'fixtures/{case}.json')
        a, b = [load(p / 'report.json') for p in paths]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
                   for r in (a, b))
        runs = [[s[k] for k in RUN_KEYS] for s in a['steps']]
        assert runs == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for section in ('stats', 'cell_ownership', 'stable_ports'):
            assert stable(a[section]) == stable(b[section]), (case, section)
        assert stable(a['stage_spine']['stats']) == stable(b['stage_spine']['stats']), case
        files = ('state.json',) if case == 'sum_bits' else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {file: sha(paths[0] / file) for file in files}
        assert all(sha(paths[1] / file) == digest for file, digest in hashes.items())
        work = {}
        for group, keys in (('stats/register_prefix', ('plan_comparisons', 'plan_index_probes', 'source_index_probes')),
                            ('stage_spine/stats', ('local_witness_route_steps', 'local_witness_route_probes',
                             'local_witness_route_index_probes', 'local_witness_route_comparisons',
                             'local_witness_read_index_probes'))):
            left, right = a, b
            for key in group.split('/'):
                left, right = left[key], right[key]
            for key in keys:
                work[f'{group}/{key}'] = [left.get(key), right[key]]
                if key not in NEW:
                    expected = (case in ('reused', 'borrowed') and key == 'plan_comparisons') or (
                        case == 'full' and key == 'local_witness_route_steps')
                    assert (left[key], right[key]) == (2, 0) if expected else left[key] == right[key]
        result['cases'][case] = {'runs': len(runs), 'ordered_hashes': hashes,
            'program_file_sha256': sha(program), 'route_work_before_after': work,
            'route_directory': b['multi_stage']['witness_plan']['route_directory']}
    a, b = [load(root / f'metrics-{lane}.json') for lane in ('baseline', 'candidate')]
    for lane, data in zip(('baseline', 'candidate'), (a, b)):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
    work = {k: v for k, v in a['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))}
    changes = {k: [v, b['metrics'][k]] for k, v in work.items() if v != b['metrics'][k]}
    assert len(work) == 326 and len(changes) == 13
    assert all(v[0]['status'] == 'missing_counter' and v[1]['status'] == 'observed'
               for v in changes.values())
    result['work_metrics'] = {'unchanged': len(work) - len(changes), 'newly_observed': changes,
        'note': 'Missing baseline counters remain missing, not zero. Direct route probes are a subset of route probes. Comparisons and witness indexes are charged separately.'}
    for name in ('checked-tests', 'credit', 'directory'):
        path = root / f'test-{name}.log'
        matches = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert matches and sum(map(int, matches)) > 0
        result['tests'][name] = {'passed': sum(map(int, matches)), 'log_sha256': sha(path)}
    minimal = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in minimal.read_text()
    result['tests']['minimal'] = {'status': 'pass', 'log_sha256': sha(minimal)}
    result['binaries'] = {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')}
    fixture_runs = load(root / 'fixtures/runs.json')
    assert len(fixture_runs) == 8
    for run in fixture_runs:
        assert run['runtime_sha256'] == result['binaries'][run['lane']]
        assert run['diagnostic_process_seconds'] < 1

    sample_path = root / 'timing/samples.json'
    data = load(sample_path)
    assert data.get('finished_at_utc') and 'failure' not in data
    assert data['repeat'] == 7 and data['warmups'] == 1
    commits = {'baseline': '7632423c', 'candidate': commit,
               'last_timed': 'd81b0cb2', 'historical': '24c4ae8a'}
    summary = {'source_sha256': sha(sample_path), 'repeat': data['repeat'], 'warmups': data['warmups'],
               'started_at_utc': data['started_at_utc'], 'finished_at_utc': data['finished_at_utc'],
               'execution_order': data['execution_order'], 'lanes': {}, 'comparisons': {}}
    rows = {}
    fields = ('inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds',
              'peak_rss_through_inference_bytes')
    for lane, values in data['lanes'].items():
        assert values['runtime_sha256'] == sha(root / f'runtime-{lane}')
        assert values['program_file_sha256'] == sha(root / 'sum/program.json')
        rows[lane] = sorted(values['samples'], key=lambda r: r['iteration'])
        assert [r['iteration'] for r in rows[lane]] == list(range(data['repeat']))
        assert all(all(r[k] == v for k, v in data['semantic_reference'].items()) for r in rows[lane])
        summary['lanes'][lane] = {'commit': commits[lane], 'runtime_sha256': values['runtime_sha256'],
            'timing': {f: TIMING['distribution']([r[f] for r in rows[lane]]) for f in fields},
            'samples': [{f: r[f] for f in ('iteration',) + fields} for r in rows[lane]]}
    for lane in ('baseline', 'last_timed', 'historical'):
        summary['comparisons'][f'candidate/{lane}'] = {
            f: TIMING['paired_ratio']([r[f] for r in rows[lane]], [r[f] for r in rows['candidate']])
            for f in ('inference_seconds', 'process_wall_seconds')}
    result['timing'] = summary
    result['limits'] = 'One short sum-bits campaign; intervals describe these interleaved samples, not equivalence or cross-machine performance. No Raytrace or complete multithread acceptance. Prefix fixtures verify behavior/work, not speed.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit), indent=2) + '\n')
