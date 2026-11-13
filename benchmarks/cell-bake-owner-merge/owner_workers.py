#!/usr/bin/env python3
"""Freeze canonical-owner control/candidate; validate before separate timing."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], text=True).strip()


def run(accepted, target, control_checkout, output):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert __debug__ and lease and lease['kind'] == 'compute'
    assert not git(ROOT, 'status', '--porcelain')
    assert not git(control_checkout, 'status', '--porcelain')
    commits = {name: git(path, 'rev-parse', 'HEAD')
               for name, path in [('control', control_checkout), ('candidate', ROOT)]}
    output.mkdir(parents=True, exist_ok=False)
    config = output / 'config'
    config.mkdir()
    manifest = json.loads((accepted / 'manifest.json').read_text())
    for case in ('sum', 'ray'):
        flags = manifest['lanes'][case]['args']
        assert '--cell-ownership' not in flags and '--stable-ports' not in flags
        manifest['lanes'][case]['args'] = [*flags, '--cell-ownership']
    (config / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    result = dict(scope='actual standalone Cell CPU; canonical-owner work and semantics, not timing',
                  commits=commits, lanes={})
    for name, checkout in [('control', control_checkout), ('candidate', ROOT)]:
        lane = output / name
        lane.mkdir()
        build = freeze(checkout, target, lane / 'runtime', lane / 'build.log',
                       'cell-absorption,view-ports,parallel-publication')
        previous = accepted if name == 'control' else output / 'control/checked'
        reference(config, lane / 'checked', lane / 'runtime', previous, commits['control'])
        workloads = {}
        for case in ('sum', 'ray'):
            report = json.loads((lane / f'checked/candidate-{case}/report.json').read_text())
            assert report['cell_ownership']['enabled']
            assert not report['stable_ports']['enabled']
            stats = report['cell_execution']['runtime']['stats']
            workloads[case] = dict(
                births={k: stats['births'][k] for k in ('local_births', 'local_reuses',
                    'worker_operations', 'root_jobs', 'slot_leases', 'slot_reattachments', 'pending_bytes')},
                scheduler={k: stats['scheduler'][k] for k in ('jobs', 'batches', 'queue_bytes', 'event_bytes')},
                ownership={k: report['cell_ownership']['stats'][k] for k in (
                    'owned_births', 'owned_live', 'signal_bindings_created',
                    'composition_result_writes', 'composition_result_joins', 'composition_baked_hits')},
                lookups=report['key_lookup_calls'])
        result['lanes'][name] = dict(build=build, workloads=workloads)
        (output / 'work.json').write_text(json.dumps(result, indent=2) + '\n')
    assert git(ROOT, 'rev-parse', 'HEAD') == commits['candidate']
    assert git(control_checkout, 'rev-parse', 'HEAD') == commits['control']
    assert not git(ROOT, 'status', '--porcelain')
    print(json.dumps({name: {case: work['births'] for case, work in lane['workloads'].items()}
                      for name, lane in result['lanes'].items()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'control_checkout', 'output'):
        parser.add_argument(name, type=Path)
    run(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
