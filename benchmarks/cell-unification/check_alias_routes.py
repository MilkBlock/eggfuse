#!/usr/bin/env python3
"""Validate saved Cell alias routing checks and the requested timing checkpoint."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS
from check_view_query import stable
from check_mixed_outputs import differences
from collect_sieve import TIMING


def same_execution(directories, programs, audit=False):
    reports = [load(p / 'report.json') for p in directories]
    for r, p in zip(reports, programs):
        assert r['status'] == 'complete' and r['program_sha256'] == load(p)['sha256']
    runs = [[[s[k] for k in RUN_KEYS] for s in r['steps']] for r in reports]
    assert all(r == runs[0] for r in runs)
    files = ('state.json', 'stages.json', 'binding-audit.json') if audit else ('state.json',)
    hashes = {f: sha(directories[0] / f) for f in files}
    assert all(sha(p / f) == h for p in directories for f, h in hashes.items())
    return dict(runs=len(runs[0]), hashes=hashes)


def clean(report):
    r = stable(work(report))
    r['steps'] = [[s[k] for k in RUN_KEYS] for s in r['steps']]
    for k in ('peak_rss_through_setup_bytes', 'peak_rss_through_inference_bytes'):
        r.pop(k)
    return r


def timing(root, commit):
    data = load(root / 'timing/samples.json')
    assert data.get('finished_at_utc') and 'failure' not in data
    assert data['repeat'] == 7 and data['warmups'] == 1
    commits = dict(baseline='135dfb1b', compatible=commit, candidate=commit,
                   last_timed='808aadb3', historical='24c4ae8a')
    assert data['lanes'].keys() == commits.keys()
    fields = ('inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds',
              'export_seconds', 'report_seconds', 'process_after_report_residual_seconds',
              'peak_rss_through_inference_bytes')
    result = dict(source_sha256=sha(root / 'timing/samples.json'), repeat=7, warmups=1,
        started_at_utc=data['started_at_utc'], finished_at_utc=data['finished_at_utc'],
        execution_order=data['execution_order'], lanes={}, comparisons={})
    rows = {}
    for lane, values in data['lanes'].items():
        binary = root / ('runtime-candidate' if lane == 'compatible' else f'runtime-{lane}')
        program = root / ('sum' if lane == 'candidate' else 'sum-old') / 'program.json'
        assert values['runtime_sha256'] == sha(binary)
        assert values['program_file_sha256'] == sha(program)
        rows[lane] = sorted(values['samples'], key=lambda r: r['iteration'])
        assert [r['iteration'] for r in rows[lane]] == list(range(7))
        assert all(all(r[k] == v for k, v in data['semantic_reference'].items()) for r in rows[lane])
        result['lanes'][lane] = dict(commit=commits[lane], runtime_sha256=sha(binary), program_file_sha256=sha(program),
            timing={f: TIMING['distribution']([r[f] for r in rows[lane]]) for f in fields},
            samples=[{f: r[f] for f in ('iteration', *fields)} for r in rows[lane]])
    for before, after in [('baseline', 'compatible'), ('compatible', 'candidate'),
                          ('baseline', 'candidate'), ('last_timed', 'candidate'), ('historical', 'candidate')]:
        result['comparisons'][f'{after}/{before}'] = {f: TIMING['paired_ratio'](
            [r[f] for r in rows[before]], [r[f] for r in rows[after]]) for f in ('inference_seconds', 'process_wall_seconds')}
    return result


def collect(root, commit, timed):
    lanes = ('baseline', 'compatible', 'candidate')
    programs = [root / d / 'program.json' for d in ('sum-old', 'sum-old', 'sum')]
    result = same_execution([root / f'run-{l}' for l in lanes], programs)
    old, new = map(load, (programs[0], programs[2]))
    assert {k: v for k, v in old.items() if k not in ('sha256', 'multi_stage')} == {
        k: v for k, v in new.items() if k not in ('sha256', 'multi_stage')}
    accepted = load(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass' and accepted['input_sha256']['cpu_values'] == result['hashes']['state.json']
    previous = Path(__file__).with_name('matched-completion-check.json')
    assert sha(root / 'runtime-baseline') == load(previous)['binaries']['candidate']
    reports = [load(root / f'run-{l}/report.json') for l in lanes]
    changes = {l: differences(clean(reports[0]), clean(r)) for l, r in zip(lanes[1:], reports[1:])}
    allowed = {'/program_sha256', '/key_lookup_calls', '/stats/decoded_rows',
               '/stage_spine/stats/local_witness_route_comparisons'}
    groups = {
        '/cell_ownership/stats/': 'domain_legacy_visits domain_planning_calls domain_queries domain_results domain_route_probes domain_signal_visits domain_slice_steps domain_type_guards domain_type_rejections',
        '/stable_ports/stats/': 'birth_hint_hits birth_hint_probes key_candidates key_field_comparisons key_lookups node_lookups port_domain_probes port_reads root_parent_probes root_resolutions',
        '/multi_stage/stats/': 'ambiguous_reads entered inverse_reads keyed_reads local_effect_reads projected_atoms published_facts residual_bindings',
        '/multi_stage/witness_plan/': 'excluded_reads physical_fallback_reads',
        '/multi_stage/witness_plan/route_directory/': 'direct_entries direct_slots read_index_capacity_bytes read_index_slots routes sparse_entries vector_capacity_bytes',
    }
    allowed.update(prefix + key for prefix, names in groups.items() for key in names.split())
    assert all(set(c) <= allowed for c in changes.values()), changes
    assert changes['candidate']['/key_lookup_calls'] == [19237, 18692]
    credits = {}
    for m in load(root / 'credit-manifest.json'):
        argv = m['argv']
        assert m['binary_sha256'] == sha(Path(argv[0]))
        assert m['reports_sha256'] == [sha(Path(p)) for p in argv[1:3]]
        value = load(Path(argv[3]))
        credits[Path(argv[3]).stem] = dict(net_saved_operations=value['net_saved_operations'],
            changed_counters={k: v for k, v in value['counters'].items() if v['saved']},
            ledger_sha256=sha(Path(argv[3])), unit=value['unit'], scope=value['scope'])
    assert [credits[f'credit-{a}-{b}']['net_saved_operations'] for a, b in
        [('baseline', 'compatible'), ('compatible', 'candidate'), ('baseline', 'candidate')]] == [5246, -1, 5245]
    fixtures = {}
    records = load(root / 'fixture-runs.json')
    expected = {(c, l, b, a) for c in ('expanded', 'retired') for l in ('baseline', 'candidate') for b in (64, 0) for a in (False, True)}
    assert len(records) == len(expected) and {(r['case'], r['lane'], r['bits'], r['audit']) for r in records} == expected
    for r in records:
        assert r['diagnostic_process_seconds'] < 1 and r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
        assert r['runtime_sha256'] == sha(Path(r['argv'][0])) and r['program_sha256'] == sha(Path(r['argv'][2]))
    for case, bits, audit in {(r['case'], r['bits'], r['audit']) for r in records}:
        p = root / f'fixture-{case}'
        fixtures[f'{case}-{bits}-{int(audit)}'] = same_execution(
            [p / f'{l}-{bits}-{int(audit)}' for l in ('baseline', 'candidate')],
            [p / f for f in ('program-old.json', 'program.json')], audit)
    tests = {}
    for name, count in [('witness', 11), ('witness-all', 11), ('matched', 3), ('publications', 9),
                        ('scoped', 12), ('credit', 4), ('barrier', 1), ('history', 1)]:
        p = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', p.read_text()))) == count
        tests[name] = dict(passed=count, sha256=sha(p))
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == new['sha256']
    metrics = []
    for l, p in zip(lanes, programs):
        m = load(root / f'metrics-{l}.json')
        assert m['sources']['report']['sha256'] == sha(root / f'run-{l}/report.json')
        assert m['sources']['program']['sha256'] == sha(p)
        metrics.append({k: v for k, v in m['metrics'].items() if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert all(m.keys() == metrics[0].keys() for m in metrics)
    metric_changes = {k: [v, metrics[2][k]] for k, v in metrics[0].items() if v != metrics[2][k]}
    opportunity = load(root / 'opportunity.json')
    result.update(scope='standalone Cell CPU; not native egglog; no allocator audit',
        candidate_commit=commit, baseline_commit='135dfb1b', semantic_acceptance='pass',
        changed_work=changes, work_credit=credits, tests=tests, fixtures=fixtures,
        binaries={l: sha(root / f'runtime-{l}') for l in ('baseline', 'candidate')},
        fixture_manifest_sha256=sha(root / 'fixture-runs.json'), recompile=load(root / 'recompile.json'),
        relower_components=len(relower['components']), previous_evidence_sha256=sha(previous),
        opportunity=dict(affected_producers=len(opportunity['affected_producers']),
            affected_operations=sum(len(p['changed_input_operations']) for p in opportunity['affected_producers']),
            affected_previously_executed_producers=sum(bool(p['prior_applied_units']) for p in opportunity['affected_producers'])),
        unchanged_work_metrics=len(metrics[0])-len(metric_changes), changed_work_metrics=metric_changes,
        limits='Singleton witness reuse supplies all 545 saved lookups. New route coverage alone scores -1 in the equal-weight ledger and adds 4524 reported static directory bytes; neither is a time/allocator measurement. Source-slot validation, liveness, visibility and delta ownership remain. General materialization, Bake composition and final parallel acceptance remain incomplete.')
    if timed:
        result['timing'] = timing(root, commit)
        result['performance_status'] = {
            comparison: {field: ('regression_observed' if v['paired_bootstrap_95_interval'][0] > 1
                else 'gain_observed' if v['paired_bootstrap_95_interval'][1] < 1 else 'unresolved')
                for field, v in values.items()}
            for comparison, values in result['timing']['comparisons'].items()}
    result['timing_cadence'] = dict(last_timed_commit=commit if timed else '808aadb3',
        implementation_commits_since_timing=0 if timed else 2,
        reason='User explicitly requested timing after this commit; resume five implementation commits thereafter.')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--timing', action='store_true')
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root.resolve(), args.commit, args.timing), indent=2) + '\n')
