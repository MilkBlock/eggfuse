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


def entry_diagnostics(root, delivery=True, names=('reused', 'replaced')):
    cases = {}
    for name in names:
        directories = [root / 'fixtures' / f'{name}-{lane}' for lane in ('baseline', 'candidate')]
        reports = [load(p / 'report.json') for p in directories]
        program = root / 'fixtures' / f'{name}.json'
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in reports)
        schedules = [[[s[k] for k in RUN_KEYS] for s in r['steps']] for r in reports]
        assert schedules[0] == schedules[1]
        hashes = {}
        for file in ('state.json', 'stages.json', 'binding-audit.json', 'rhs.json', 'writes.json', 'resumes.json'):
            hashes[file] = sha(directories[0] / file)
            assert hashes[file] == sha(directories[1] / file), (name, file)
        a, b = [r['stats']['register_prefix'] for r in reports]
        if delivery:
            assert b['entry_publication_reads'] == a['publication_probes'] > 0
            assert b['publication_probes'] == 0
            assert b['context_reads'] < a['context_reads']
            if name == 'reused':
                assert b['context_reads'] == 0
            else:
                assert b['context_reads'] > 0  # the uncovered replacement still recovers its physical source
                assert reports[1]['entry_schedule']['stats']['entry_publications_retired'] > 0
            assert b['receipt_hits'] > 0
            assert all(b[k] == v for k, v in a.items() if k not in ('context_reads', 'publication_probes'))
        else:
            assert a == b, (name, 'prefix work')
            assert b['receipt_hits'] > 0
        assert reports[0]['key_lookup_calls'] == reports[1]['key_lookup_calls']
        borrowed_work = None
        if name == 'borrowed':
            stats = reports[1]['stats']
            assert stats['register_expansion_rows'] > 0
            assert stats['register_result_writes'] > b['field_writes']
            borrowed_work = {k: stats[k] for k in ('register_expansion_rows', 'register_result_writes')}
        cases[name] = {
            'scope': 'short standalone Cell CPU diagnostic; source fixtures shared with differential/native-check tests',
            'program_file_sha256': sha(program), 'ordered_runs': len(reports[0]['steps']),
            'ordered_hashes': hashes, 'prefix': {'baseline': a, 'candidate': b},
            'seed_bytes': reports[1]['entry_schedule']['seed_bytes'],
            'borrowed_field_work': borrowed_work,
        }
    runs = load(root / 'fixtures/runs.json')
    assert {(r['case'], r['lane']) for r in runs} == {(c, l) for c in cases for l in ('baseline', 'candidate')}
    assert all(r['diagnostic_process_seconds'] < 1 for r in runs)
    assert all(r['runtime_sha256'] == sha(root / f"runtime-{r['lane']}-audit") for r in runs)
    return {'cases': cases, 'runs': runs, 'timing_scope': 'duration only verifies the short-fixture budget; not a performance measurement'}


def collect(root, part='definition'):
    result_ports = part == 'result-ports'
    entry_delivery = part == 'entry-delivery'
    query = part == 'query'
    residual = part == 'residual'
    publication = part == 'publication'
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
    if result_ports or entry_delivery or query or residual or publication:
        # New counters are reported as newly observed, never as a reduction
        # from an invented zero in the older runtime.
        new_fields = {
            'result-ports': ('/history_result_reads', '/history_empty_slots_written',
                             '/local_witness_slot_reads', '/register_prefix/receipt_slot_reads'),
            'entry-delivery': ('/entry_schedule/seed_bytes', '/register_prefix/entry_publication_reads'),
            'residual': ('/stats/register_result_writes', '/stats/register_expansion_rows', '/stage_spine/shared_query_plans'),
            'publication': ('/entry_schedule/stats/publication_candidate_checks', '/entry_schedule/stats/publication_loser_skips',
                            '/stage_spine/stats/completion_boundary_records', '/stage_spine/stats/completion_boundary_reads',
                            '/stage_spine/stats/completion_order_checks', '/stage_spine/stats/completion_cell_visits',
                            '/stage_spine/stats/completion_cursor_moves'),
            'query': ('/stage_spine/stats/cell_query_entries', '/stage_spine/stats/cell_query_steps',
                      '/stage_spine/stats/cell_query_result_writes'),
        }[part]
        added = {k: v for k, v in changes.items() if any(f in k for f in new_fields)}
        assert len(added) == len(new_fields), added
        assert all(v['before']['status'] == 'missing_counter' and
                   v['after']['status'] == 'observed' for v in added.values())
        changes = {k: v for k, v in changes.items() if k not in added}
    if publication:
        removed = ('fragment_pending_writes', 'fragment_pending_reads', 'fragment_slot_probes',
                   'fragment_slot_replacements', 'fragment_older_skips')
        assert len(changes) == len(removed), changes
        assert all(any(f'/entry_schedule/stats/{name} ' in k for name in removed)
                   and v['before']['value'] > 0 and v['after']['value'] == 0
                   for k, v in changes.items()), changes
        entries = reports[1]['entry_schedule']['stats']
        spine = reports[1]['stage_spine']['stats']
        assert entries['publication_candidate_checks'] == entries['entry_publication_writes'] + entries['publication_loser_skips']
        assert spine['completion_boundary_records'] == spine['completion_boundary_reads']
        for name in ('fragment_pending_reads', 'fragment_pending_writes', 'fragment_slot_probes',
                     'fragment_slot_replacements', 'fragment_older_skips'):
            assert entries[name] == 0
    else:
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
        if result_ports or entry_delivery or query or residual or publication:
            # Runtime result retention must not add allocations. Compile-time
            # layout storage belongs to program loading (outside these two
            # allocation regions); process wall time and RSS include it.
            if region == 'allocations' or entry_delivery or query or residual or publication:
                assert all(b[k] <= a[k] for k in fields), region
        elif region == 'allocations':
            assert all(a[k] == b[k] for k in fields), region
        else:
            # Setup's producer classification now inspects the borrowed Cell
            # relation instead of allocating and normalizing a column vector.
            assert all(b[k] <= a[k] for k in fields), region
        if not (result_ports or entry_delivery or query or residual or publication):
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
    supplemental = None
    if query:
        log = root / 'test-query-integration.log'
        assert re.search(r'test result: ok\. 1 passed; 0 failed', log.read_text())
        supplemental = {'passed': 1, 'log_sha256': sha(log),
                        'scope': 'repeat of the stage-entry integration test after adding shared-path coverage assertions; not an additional distinct test'}
    if publication:
        log = root / 'test-publication-partial.log'
        assert re.search(r'test result: ok\. 1 passed; 0 failed', log.read_text())
        supplemental = {'passed': 1, 'log_sha256': sha(log),
                        'scope': 'partial-scope fragment publication without global audit fences; same test also included in compiler suite'}
    earlier = None
    if (result_ports or entry_delivery or residual) and (root / 'first-attempt/results.json').exists():
        trial = load(root / 'first-attempt/results.json')
        earlier = {
            'status': ('revised after a roughly 1% paired inference regression' if result_ports else
                       'no demonstrated inference gain and higher peak RSS; removed redundant artifact JSON copying and borrowed bound-result checks' if residual else
                       'inconclusive timing; inspected and reduced out-of-line Entry return-value copies'),
            'runtime_sha256': trial['binaries']['runtime-candidate'],
            'paired_timing_ratios': trial['paired_timing_ratios'],
            'revision': ('compact ResultPort to 8 bytes; write present slots once; count padding during capture instead of scanning the frame again' if result_ports else
                         'move prebuilt wire JSON arrays into parents; common BoundStep borrows expected values instead of cloning them' if residual else
                         'add inline hint to the shared borrowed Entry accessor; matching closure and iterator call sites disappear'),
            'scope': 'intermediate uncommitted implementation; retained as experiment history, not a second final acceptance run',
        }
    return {
        'scope': f'standalone Cell CPU; {part} rewrite, not completion of the unification goal',
        'baseline_commit': {'definition': '27f1c503', 'result-ports': 'd36e0254', 'entry-delivery': 'e275f3db', 'query': '4b5070cf', 'residual': '9dfe6986', 'publication': 'ec6586d4'}[part],
        'program_file_sha256': sha(program),
        'binaries': {name: sha(root / name) for name in ('runtime-baseline', 'runtime-candidate',
                                                       'runtime-baseline-audit', 'runtime-candidate-audit')},
        'normal_features': 'sparse-cells,view-ports,storage-metrics',
        'diagnostic_extra_features': 'allocation-metrics,slot-transfer-audit,spine-shapes',
        'build_provenance': ('frozen previous-step binaries; candidate built in this worktree only, separate normal/audit target directories'
                             if result_ports or entry_delivery or query or residual or publication else 'shared Cargo target diagnostic discarded; candidate rebuilt in target/cell-unification-audit'),
        'semantic_acceptance': semantics, 'compiler_components': relower,
        'native_reference_scope': 'source emitter unchanged; native legacy/values labels intentionally share the same marked-source export',
        'ordered_runs': len(schedule[0]), 'ordered_audit_hashes': hashes, 'tests': tests,
        'supplemental_test': supplemental,
        'metric_count': len(before), 'preserved_work_metric_statuses': dict(Counter(v['status'] for k, v in work.items() if k not in added and k not in changes)),
        'optimization_groups_tracked': len(coverage['optimizations']),
        'work_metric_changes': changes, 'newly_observed_metrics': added, 'allocations': allocations,
        'timing': timing, 'paired_timing_ratios': ratios, 'repeat': raw['repeat'], 'warmups': raw['warmups'],
        'earlier_attempt': earlier,
        'entry_diagnostics': (entry_diagnostics(root, delivery=entry_delivery, names=('reused', 'replaced', 'borrowed') if residual or publication else ('reused', 'replaced'))
                              if entry_delivery or query or residual or publication else None),
        'entry_accessor_call_sites': ({'calls': load(root / 'entry-view-calls.json'),
                                      'scope': 'static disassembly call sites, not runtime call counts'}
                                     if entry_delivery and (root / 'entry-view-calls.json').exists() else None),
        'performance_acceptance': ('unresolved: short-sample inference median is slightly slower and paired interval is wide; structural takeover does not prove an end-to-end speedup'
                                   if entry_delivery else 'unresolved: paired inference and process intervals include parity; peak RSS remains higher despite lower execute allocation bytes'
                                   if residual else 'inference unresolved: paired interval includes parity; process wall interval is below parity in this short sample only; no general workload or overall-goal performance claim'
                                   if publication else 'see paired samples; no general workload claim'),
        'limitations': ['short sum-bits preservation check; no new Raytrace or historical-fastest campaign',
                        'allocation regions exclude program loading; process wall time and RSS include that cost',
                        'same work counts do not prove the remaining execution paths have been rewritten',
                        'whole-graph hashes are determinism diagnostics in addition to the semantic acceptance script'],
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--part', choices=('definition', 'result-ports', 'entry-delivery', 'query', 'residual', 'publication'), default='definition')
    args = p.parse_args()
    if not __debug__:
        raise SystemExit('run without -O; assertions are verification checks')
    args.output.write_text(json.dumps(collect(args.root, args.part), indent=2, ensure_ascii=False) + '\n')
