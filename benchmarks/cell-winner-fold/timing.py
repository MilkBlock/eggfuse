#!/usr/bin/env python3
"""Prepare/collect the five-change checkpoint; measurement uses the existing harness."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess

REPO = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    old = read(REPO / 'benchmarks/cell-handoff-merge/ray-samples.json')['lanes']
    configs = {
        'historical_serial': ('out/cell-history-forwarding/runtime-candidate', 0, 'historical_serial'),
        'historical_inline1': ('out/cell-entry-partition/runtime-final', 1, 'before_inline1'),
        'checkpoint4': ('out/cell-handoff-merge/runtime-final', 4, 'after_query4'),
        'before4': (str(root / 'runtime-before'), 4, None),
        'current_off': (str(root / 'runtime-after'), 0, None),
        'current_inline1': (str(root / 'runtime-after'), 1, None),
        'current4': (str(root / 'runtime-after'), 4, None),
    }
    provenance = {
        'scope': 'Standalone Cell CPU; same frozen program and catalog in all lanes; no native egglog timing.',
        'candidate_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'immediate_baseline': 'c8d0584b',
        'checkpoint': 'c8b099fd merge snapshot, as identified in cell-handoff-merge',
        'historical_inline1': '168285bd',
        'features': 'sparse-cells,view-ports,storage-metrics; release; no allocation-metrics',
        'platform': platform.platform(),
        'cpu': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
        'binaries': {},
    }
    short = read(root / 'checks/checks.json')
    assert short['semantic_acceptance']['status'] == 'pass'
    for name, (binary, _, reference) in configs.items():
        path = (REPO / binary).resolve()
        digest = sha(path)
        if reference:
            assert digest == old[reference]['runtime_sha256'], name
        elif name == 'before4':
            assert digest == short['binaries']['baseline']
        else:
            assert digest == short['binaries']['candidate']
        provenance['binaries'][name] = {'path': str(path), 'sha256': digest}
    for workload, program in [('sum', 'out/cell-history-forwarding/sum/program.json'),
                              ('ray', 'out/raytrace-thread-bottlenecks/query-classes/program.json')]:
        program = (REPO / program).resolve()
        save(root / f'{workload}-manifest.json', {'lanes': {
            name: {'runtime': provenance['binaries'][name]['path'], 'program': str(program),
                   'args': ['--local-congruence'] + (['--query-workers', str(workers),
                            '--query-grain', '64'] if workers else [])}
            for name, (_, workers, _) in configs.items()}})
    save(root / 'timing-provenance.json', provenance)


def collect(root, output):
    helpers = runpy.run_path(str(REPO / 'benchmarks/raytrace-parallel/collect.py'))
    dist, ratio = helpers['distribution'], helpers['paired_ratio']
    provenance = read(root / 'timing-provenance.json')
    result = {'scope': provenance['scope'], 'provenance': provenance, 'workloads': {},
              'limits': 'Three interleaved samples on an interactive machine. Same runtime graphs and '
                        'ordered Run signatures are regression checks, not independent native Raytrace proof. '
                        'No engine edits or compilation during timing. Older comparison counters omit the '
                        'second key sort and are not directly comparable to the fused comparator.'}
    for workload, runs in [('sum', 1428), ('ray', 16883)]:
        path = root / f'{workload}-timing/samples.json'
        source = read(path)
        assert source.get('finished_at_utc') and 'failure' not in source
        compact = {k: source[k] for k in ['scope', 'repeat', 'warmups', 'started_at_utc',
                   'finished_at_utc', 'execution_order', 'semantic_reference']}
        compact.update(raw_samples_sha256=sha(path), lanes={})
        summary = {'repeat': source['repeat'], 'warmups': source['warmups'],
                   'semantic_reference': source['semantic_reference'], 'lanes': {}, 'comparisons': {}}
        for name, lane in source['lanes'].items():
            assert lane['runtime_sha256'] == provenance['binaries'][name]['sha256']
            assert sha(Path(provenance['binaries'][name]['path'])) == lane['runtime_sha256']
            rows = sorted(lane['samples'], key=lambda r: r['iteration'])
            assert [r['iteration'] for r in rows] == list(range(source['repeat']))
            for row in [*lane['warmup_samples'], *rows]:
                assert row['runs'] == runs
                assert {k: row[k] for k in source['semantic_reference']} == source['semantic_reference']
                q = row.get('query_workers') or {'enabled': False}
                if q['enabled']:
                    s = q['stats']
                    assert s['entries'] == sum(s['worker_entries']) + s['coordinator_entries']
            fields = ['iteration', 'inference_seconds', 'process_wall_seconds', 'process_user_seconds',
                      'process_system_seconds', 'setup_seconds', 'load_seconds', 'report_seconds',
                      'export_seconds', 'peak_rss_through_inference_bytes', 'phases', 'key_lookup_calls',
                      'runs', 'state_sha256', 'schedule_sha256']
            compact['lanes'][name] = {k: lane[k] for k in ['args', 'runtime_sha256', 'program_file_sha256']}
            compact['lanes'][name].update({k: [{f: r[f] for f in fields} for r in lane[k]]
                                          for k in ['warmup_samples', 'samples']})
            summary['lanes'][name] = {
                'timing': {k: dist([r[k] for r in rows]) for k in ['inference_seconds',
                    'process_wall_seconds', 'setup_seconds', 'peak_rss_through_inference_bytes']},
                'phases': {k: dist([r['phases'][k] for r in rows]) for k in rows[0]['phases']},
                'query_workers_first_sample': rows[0]['query_workers'],
                'cell_handoff_work_first_sample': {k: rows[0]['stage_spine_stats'].get(k) for k in [
                    'effect_slots_initialized', 'history_capture_reads', 'history_slots_written',
                    'history_shared_slots', 'joint_history_checks', 'joint_history_frames',
                    'joint_history_query_reads', 'joint_history_query_writes', 'joint_output_reads',
                    'cell_output_registrations', 'output_registrations', 'query_fragment_sealed_slots']},
                'missing_work_metric_policy': 'null means absent in this older report, not zero'}
        for before in ['historical_serial', 'historical_inline1', 'checkpoint4', 'before4',
                       'current_off', 'current_inline1']:
            a, b = [sorted(source['lanes'][n]['samples'], key=lambda r: r['iteration'])
                    for n in [before, 'current4']]
            summary['comparisons'][f'current4/{before}'] = {
                k: ratio([r[k] for r in a], [r[k] for r in b])
                for k in ['inference_seconds', 'process_wall_seconds']}
        result['workloads'][workload] = summary
        save(output / f'{workload}-samples.json', compact)
    save(output / 'timing.json', result)
    print(json.dumps({w: {n: v['timing']['inference_seconds']['median'] for n, v in s['lanes'].items()}
                      for w, s in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['prepare', 'collect'])
    p.add_argument('root', type=Path)
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = p.parse_args()
    if args.command == 'prepare':
        prepare(args.root.resolve())
    else:
        collect(args.root.resolve(), args.output.resolve())
