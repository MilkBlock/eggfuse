#!/usr/bin/env python3
"""Freeze canonical-owner control/candidate; validate before separate timing."""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], text=True).strip()


def run(accepted, target, control_checkout, output, learned_program=None, reuse_control=None):
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
        if name == 'control' and reuse_control is not None:
            prior = json.loads((reuse_control / 'work.json').read_text())
            assert prior['commits']['control'] == commits['control']
            sha = runpy.run_path(str(ROOT / 'benchmarks/cell-bake-full-merge/check.py'))['sha']
            assert sha(reuse_control / 'control/runtime') == prior['lanes']['control']['build']['runtime_sha256']
            old_config = json.loads((reuse_control / 'config/manifest.json').read_text())
            assert old_config['lanes'] == manifest['lanes']
            if learned_program is not None:
                assert sha(learned_program) == prior['learned_validation']['program_sha256']
            shutil.copytree(reuse_control / 'control', lane)
            result['lanes']['control'] = prior['lanes']['control']
            result['reused_control'] = str(reuse_control)
            continue
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
                lookups=report['key_lookup_calls'], preparation=prefix_work(report))
        result['lanes'][name] = dict(build=build, workloads=workloads)
        if learned_program is not None:
            destination = lane / 'learned'
            command = [str(lane / 'runtime'), '--program', str(learned_program),
                       '--output', str(destination), *manifest['lanes']['sum']['args']]
            with (lane / 'learned.log').open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            report = json.loads((destination / 'report.json').read_text())
            assert report['status'] == 'complete' and report['cell_ownership']['enabled']
            result['lanes'][name]['learned'] = prefix_work(report)
        (output / 'work.json').write_text(json.dumps(result, indent=2) + '\n')
    if learned_program is not None:
        helpers = runpy.run_path(str(ROOT / 'benchmarks/cell-bake-full-merge/check.py'))
        keys = runpy.run_path(str(ROOT / 'benchmarks/raytrace-parallel/measure.py'))['KEYS']
        a, b = [json.loads((output / name / 'learned/report.json').read_text())
                for name in ('control', 'candidate')]
        assert a['program_sha256'] == b['program_sha256']
        assert [[s[k] for k in keys] for s in a['steps']] == [[s[k] for k in keys] for s in b['steps']]
        effects = ('bindings', 'constructor_requests', 'constructor_reused', 'logical_facts_created',
                   'function_updates', 'union_requests', 'unions', 'merge_calls')
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        state_hash = helpers['sha'](output / 'control/learned/state.json')
        assert state_hash == helpers['sha'](output / 'candidate/learned/state.json')
        result['learned_validation'] = dict(
            scope='unchanged saved Bake catalog; differential final state, Run summaries and effects; not native acceptance or timing',
            program_sha256=helpers['sha'](learned_program), state_sha256=state_hash,
            exact_state_runs_effects=True, runs=len(a['steps']))
        (output / 'work.json').write_text(json.dumps(result, indent=2) + '\n')
    assert git(ROOT, 'rev-parse', 'HEAD') == commits['candidate']
    assert git(control_checkout, 'rev-parse', 'HEAD') == commits['control']
    assert not git(ROOT, 'status', '--porcelain')
    print(json.dumps({name: {case: work['births'] for case, work in lane['workloads'].items()}
                      for name, lane in result['lanes'].items()}, indent=2))


def prefix_work(report):
    return dict(lookups=report['key_lookup_calls'],
                source={k: v for k, v in report['stats'].items() if k.startswith('constructor_prefix_')},
                worker=report['query_workers']['stats']['execution']['constructor'],
                results={k: v for k, v in report['stage_spine']['stats'].items()
                         if k.startswith(('prepared_effect_', 'effect_buffer_'))},
                ownership={k: v for k, v in report['cell_ownership']['stats'].items()
                           if k.startswith(('composition_', 'witness_'))})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'control_checkout', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--learned-program', type=Path,
                        help='also audit an unchanged saved catalog; outside native contract and timing')
    parser.add_argument('--reuse-control', type=Path,
                        help='reuse a frozen, validated control from the identical source commit and inputs')
    run(**{k: v.resolve() if v is not None else None for k, v in vars(parser.parse_args()).items()})
