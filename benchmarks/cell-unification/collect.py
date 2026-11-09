#!/usr/bin/env python3
"""Collect Cell rewrite preservation evidence from existing checks and samples.

Does not run workloads. Timing uses the existing witness-prefix process harness;
semantic acceptance and metric extraction use their existing repository scripts.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy

REPO = Path(__file__).resolve().parents[2]
TIMING = runpy.run_path(str(REPO / 'benchmarks/raytrace-parallel/collect.py'))
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(root, part='definition'):
    result_ports = part == 'result-ports'
    catalog = load(REPO / 'docs/optimization-catalog/catalog.json')
    coverage = load(REPO / 'benchmarks/cell-unification/coverage.json')
    assert {x['id'] for x in coverage['optimizations']} == {x['id'] for x in catalog['optimizations']}
    semantics = load(root / 'semantic-acceptance.json')
    relower = load(root / 'relower.json')
    assert semantics['status'] == relower['status'] == 'pass'
    program = root / 'sum/program.json'
    reports = [load(root / f'run-{lane}/report.json') for lane in ('baseline', 'candidate')]
    assert all(r['status'] == 'complete' and r['program_sha256'] == relower['program_sha256'] for r in reports)
    schedule = [[[s[k] for k in RUN_KEYS] for s in r['steps']] for r in reports]
    assert schedule[0] == schedule[1]
    assert sha(root / 'run-baseline/state.json') == sha(root / 'run-candidate/state.json')

    extracted = [load(root / f'metrics-{lane}.json') for lane in ('baseline', 'candidate')]
    for lane, data in zip(('baseline', 'candidate'), extracted):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
    before, after = [x['metrics'] for x in extracted]
    assert before.keys() == after.keys()
    # Timing and RSS are measured separately, rather than treated as operations.
    resource = lambda k: any(x in k for x in ('_seconds', '_ns ', '/phases/', 'peak_rss'))
    work = {k: v for k, v in before.items() if not resource(k)}
    changes = {k: {'before': v, 'after': after[k]} for k, v in work.items() if v != after[k]}
    added = {}
    if result_ports:
        # New counters are reported as newly observed, never as a reduction
        # from an invented zero in the older runtime.
        new_fields = ('/history_result_reads', '/history_empty_slots_written',
                      '/local_witness_slot_reads', '/register_prefix/receipt_slot_reads')
        added = {k: v for k, v in changes.items() if any(f in k for f in new_fields)}
        assert len(added) == 4, added
        assert all(v['before']['status'] == 'missing_counter' and
                   v['after']['status'] == 'observed' for v in added.values())
        changes = {k: v for k, v in changes.items() if k not in added}
    assert not changes, changes

    audit = [load(root / f'audit-{lane}/report.json') for lane in ('baseline', 'candidate')]
    assert all(r['status'] == 'complete' and r['program_sha256'] == relower['program_sha256'] for r in audit)
    hashes = {}
    for file in ('state.json', 'rhs.json', 'writes.json', 'resumes.json'):
        hashes[file] = sha(root / 'audit-baseline' / file)
        assert hashes[file] == sha(root / 'audit-candidate' / file), file
    allocations = {}
    # Absolute live bytes include command-line strings. Compare requests/frees
    # and growth during the measured region, preserving absolute readings too.
    fields = ('alloc_calls', 'realloc_calls', 'free_calls', 'requested_bytes', 'released_bytes')
    for region in ('setup_allocations', 'allocations'):
        a, b = [r[region] for r in audit]
        if result_ports:
            # Runtime result retention must not add allocations. Compile-time
            # layout storage belongs to program loading (outside these two
            # allocation regions); process wall time and RSS include it.
            if region == 'allocations':
                assert all(b[k] <= a[k] for k in fields), region
        elif region == 'allocations':
            assert all(a[k] == b[k] for k in fields), region
        else:
            # Setup's producer classification now inspects the borrowed Cell
            # relation instead of allocating and normalizing a column vector.
            assert all(b[k] <= a[k] for k in fields), region
        if not result_ports:
            assert a['live_bytes_after'] - a['live_bytes_before'] == b['live_bytes_after'] - b['live_bytes_before']
        allocations[region] = {'baseline': a, 'candidate': b,
                               'saved': {k: a[k] - b[k] for k in fields}}
    assert sha(root / 'runtime-baseline-audit') != sha(root / 'runtime-candidate-audit'), 'check isolated build provenance'

    raw = load(root / 'timing/samples.json')
    assert raw.get('finished_at_utc') and 'failure' not in raw
    timing = {}
    for name, lane in raw['lanes'].items():
        assert lane['runtime_sha256'] == sha(root / f'runtime-{name}')
        assert lane['program_file_sha256'] == sha(program)
        for row in lane['samples'] + lane['warmup_samples']:
            assert all(row[k] == v for k, v in raw['semantic_reference'].items())
        timing[name] = {k: TIMING['distribution']([r[k] for r in lane['samples']])
                       for k in ('inference_seconds', 'process_wall_seconds', 'peak_rss_through_inference_bytes')}
        timing[name]['samples'] = [{k: r[k] for k in ('iteration', 'inference_seconds', 'process_wall_seconds')}
                                   for r in lane['samples']]
    ratios = {k: TIMING['paired_ratio']([r[k] for r in raw['lanes']['baseline']['samples']],
                                       [r[k] for r in raw['lanes']['candidate']['samples']])
              for k in ('inference_seconds', 'process_wall_seconds')}
    tests = {}
    for name in ('compiler', 'runtime-all', 'runtime-minimal'):
        log = root / f'test-{name}.log'
        groups = re.findall(r'test result: (\w+)\. (\d+) passed; (\d+) failed', log.read_text())
        assert groups and all(status == 'ok' and int(failed) == 0 for status, _, failed in groups)
        tests[name] = {'passed': sum(int(passed) for _, passed, _ in groups), 'log_sha256': sha(log)}
    earlier = None
    if result_ports and (root / 'first-attempt/results.json').exists():
        trial = load(root / 'first-attempt/results.json')
        earlier = {
            'status': 'revised after a roughly 1% paired inference regression',
            'runtime_sha256': trial['binaries']['runtime-candidate'],
            'paired_timing_ratios': trial['paired_timing_ratios'],
            'revision': 'compact ResultPort to 8 bytes; write present slots once; count padding during capture instead of scanning the frame again',
            'scope': 'intermediate uncommitted implementation; retained as experiment history, not a second final acceptance run',
        }
    return {
        'scope': f'standalone Cell CPU; {part} rewrite, not completion of the unification goal',
        'baseline_commit': 'd36e0254' if result_ports else '27f1c503', 'program_file_sha256': sha(program),
        'binaries': {name: sha(root / name) for name in ('runtime-baseline', 'runtime-candidate',
                                                       'runtime-baseline-audit', 'runtime-candidate-audit')},
        'normal_features': 'sparse-cells,view-ports,storage-metrics',
        'diagnostic_extra_features': 'allocation-metrics,slot-transfer-audit,spine-shapes',
        'build_provenance': ('frozen d36e0254 binaries; candidate built in this worktree only, separate normal/audit target directories'
                             if result_ports else 'shared Cargo target diagnostic discarded; candidate rebuilt in target/cell-unification-audit'),
        'semantic_acceptance': semantics, 'compiler_components': relower,
        'native_reference_scope': 'source emitter unchanged; native legacy/values labels intentionally share the same marked-source export',
        'ordered_runs': len(schedule[0]), 'ordered_audit_hashes': hashes, 'tests': tests,
        'metric_count': len(before), 'preserved_work_metric_statuses': dict(Counter(v['status'] for k, v in work.items() if k not in added)),
        'optimization_groups_tracked': len(coverage['optimizations']),
        'work_metric_changes': changes, 'newly_observed_metrics': added, 'allocations': allocations,
        'timing': timing, 'paired_timing_ratios': ratios, 'repeat': raw['repeat'], 'warmups': raw['warmups'],
        'earlier_attempt': earlier,
        'limitations': ['short sum-bits preservation check; no new Raytrace or historical-fastest campaign',
                        'allocation regions exclude program loading; process wall time and RSS include that cost',
                        'same work counts do not prove the remaining execution paths have been rewritten',
                        'whole-graph hashes are determinism diagnostics in addition to the semantic acceptance script'],
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--part', choices=('definition', 'result-ports'), default='definition')
    args = p.parse_args()
    if not __debug__:
        raise SystemExit('run without -O; assertions are verification checks')
    args.output.write_text(json.dumps(collect(args.root, args.part), indent=2, ensure_ascii=False) + '\n')
