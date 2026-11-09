#!/usr/bin/env python3
"""Collect the lifecycle rewrite checkpoint, retaining all timing attempts.

Reads saved checks; does not build or run workloads. See steps.md for the
rewrite and lifecycle-*-timing-spec.json for the interleaved timing inputs.
"""
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
FIELDS = ('inference_seconds', 'process_wall_seconds', 'load_seconds',
          'setup_seconds', 'peak_rss_through_inference_bytes')
COMMITS = {
    'baseline': 'f760e24f', 'candidate': '9f767036', 'revised': '55392d47',
    'final': 'd81b0cb2', 'checkpoint': '24c4ae8a',
}
TIMINGS = {
    'initial': ('timing', {'baseline': 'f760e24f', 'candidate': '9f767036',
                         'checkpoint': '24c4ae8a'}),
    'localization': ('timing-localization', {'checkpoint': '24c4ae8a',
                     'propagation': 'b01f9984', 'field_uses': 'f760e24f'}),
    'inline_hint': ('timing-inline', {'baseline': '9f767036',
                   'candidate': '55392d47', 'checkpoint': '24c4ae8a'}),
    'inline_always': ('timing-final', {'baseline': '9f767036',
                     'candidate': 'd81b0cb2', 'checkpoint': '24c4ae8a'}),
}


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root):
    semantics = load(root / 'semantic-acceptance.json')
    assert semantics['status'] == 'pass'
    result = {
        'scope': 'standalone Cell CPU; normal release short sum-bits; not native egglog timing',
        'normal_features': 'sparse-cells,view-ports,storage-metrics',
        'commits': COMMITS, 'semantic_acceptance': semantics['status'],
        'performance_status': 'preservation_unresolved_no_speedup_established',
        'interpretation': 'The initial timing found a regression. Later trials are noisy and do not prove its removal. Static call removal is not a measured speedup. All four trials are retained; small-sample bootstrap intervals are not equivalence tests or cross-machine guarantees.',
        'cases': {}, 'tests': {}, 'timing_trials': {},
    }
    for case, prefix, program, files in (
        ('sum_bits', 'run', 'sum/program.json', ('state.json',)),
        ('port_fixture', 'port', 'port-program.json',
         ('state.json', 'stages.json', 'binding-audit.json')),
    ):
        dirs = [root / f'{prefix}-{lane}' for lane in ('baseline', 'candidate', 'revised', 'final')]
        reports = [load(p / 'report.json') for p in dirs]
        assert all(r['status'] == 'complete' and
                   r['program_sha256'] == load(root / program)['sha256'] for r in reports)
        reference = [[s[k] for k in RUN_KEYS] for s in reports[0]['steps']]
        for report in reports[1:]:
            assert [[s[k] for k in RUN_KEYS] for s in report['steps']] == reference
            for section in ('stats', 'cell_ownership', 'stable_ports'):
                assert report[section] == reports[0][section], (case, section)
        hashes = {}
        for file in files:
            hashes[file] = sha(dirs[0] / file)
            assert all(sha(p / file) == hashes[file] for p in dirs[1:])
        result['cases'][case] = {
            'runs': len(reference), 'program_file_sha256': sha(root / program),
            'ordered_hashes': hashes, 'runtime_ownership_and_stable_counters_identical': True,
        }

    extracted = [load(root / f'metrics-{lane}.json')
                 for lane in ('baseline', 'candidate', 'revised', 'final')]
    for lane, data in zip(('baseline', 'candidate', 'revised', 'final'), extracted):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
    work = {k: v for k, v in extracted[0]['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))}
    assert all(all(data['metrics'][k] == v for k, v in work.items()) for data in extracted[1:])
    result['unchanged_work_metrics'] = len(work)
    result['observed_work_metrics'] = sum(v['status'] == 'observed' for v in work.values())
    result['metric_note'] = 'Unchanged compares values and missing-counter status; no allocation audit was run in this group. Relative to the checkpoint, the field-use change remains as recorded in field-uses-check.json.'

    for name in ('init-address', 'init-stages', 'init-retirement', 'init-legacy',
                 'native-waves', 'native-retained', 'native-classes', 'inline'):
        p = root / f'test-{name}.log'
        log = p.read_text()
        matches = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', log)
        assert matches and sum(map(int, matches)) > 0, name
        result['tests'][name] = {'passed': sum(map(int, matches)), 'log_sha256': sha(p)}
    for name in ('init-minimal', 'native-minimal'):
        p = root / f'test-{name}.log'
        assert 'Finished `dev` profile' in p.read_text()
        result['tests'][name] = {'status': 'pass', 'log_sha256': sha(p)}
    result['static_field_use_call_sites'] = {
        name: len(load(root / f'field-use-calls-{file}.json'))
        for name, file in (('before', 'before'), ('inline_hint', 'after'), ('inline_always', 'final'))
    }
    assert result['static_field_use_call_sites'] == {'before': 3, 'inline_hint': 2, 'inline_always': 0}
    result['assembly_note'] = 'AArch64 bl instructions naming FieldUses::fact in llvm-objdump --disassemble --demangle; static sites, not runtime invocation counts.'
    result['binaries'] = {COMMITS[lane]: sha(root / f'runtime-{lane}') for lane in COMMITS}
    result['binaries']['b01f9984'] = sha(root.parent / 'cell-propagation-unified/runtime-candidate')

    for trial, (directory, commits) in TIMINGS.items():
        source = root / directory / 'samples.json'
        data = load(source)
        assert data.get('finished_at_utc') and 'failure' not in data
        assert data['repeat'] == 7 and data['warmups'] == 1
        rows = {}
        summary = {'source_sha256': sha(source), 'repeat': data['repeat'],
                   'warmups': data['warmups'], 'started_at_utc': data['started_at_utc'],
                   'finished_at_utc': data['finished_at_utc'], 'lanes': {}, 'comparisons': {}}
        for lane, value in data['lanes'].items():
            assert value['runtime_sha256'] == result['binaries'][commits[lane]]
            assert value['program_file_sha256'] == sha(root / 'sum/program.json')
            rows[lane] = sorted(value['samples'], key=lambda r: r['iteration'])
            assert [r['iteration'] for r in rows[lane]] == list(range(data['repeat']))
            assert all(all(r[k] == v for k, v in data['semantic_reference'].items()) for r in rows[lane])
            summary['lanes'][lane] = {
                'commit': commits[lane],
                'timing': {f: TIMING['distribution']([r[f] for r in rows[lane]]) for f in FIELDS},
                'samples': [{f: r[f] for f in ('iteration',) + FIELDS} for r in rows[lane]],
            }
        candidate = 'candidate' if 'candidate' in rows else 'field_uses'
        for reference in rows:
            if reference != candidate:
                summary['comparisons'][candidate + '/' + reference] = {
                    f: TIMING['paired_ratio']([r[f] for r in rows[reference]],
                                             [r[f] for r in rows[candidate]])
                    for f in ('inference_seconds', 'process_wall_seconds')
                }
        result['timing_trials'][trial] = summary
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(args.root), indent=2) + '\n')
