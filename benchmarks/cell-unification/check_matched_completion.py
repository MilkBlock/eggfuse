#!/usr/bin/env python3
"""Check saved matched-Cell completion and source-boundary runs; never time them."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS
from check_view_query import stable
from check_mixed_outputs import differences


def compare(root, lanes, program, audit=False):
    reports = [load(root / lane / 'report.json') for lane in lanes]
    coverage = reports[1]['stats']['matched_cells_completed']
    assert isinstance(coverage, int) and coverage >= 0
    clean = [stable(work(r)) for r in reports]
    for r in clean:
        assert r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
        # The old binary lacks this new coverage counter. Do not invent an old
        # measured zero or count it again as rhs_frames_avoided / work credit.
        r['stats'].pop('matched_cells_completed', None)
        r['steps'] = [[s[k] for k in RUN_KEYS] for s in r['steps']]
        for k in ('peak_rss_through_setup_bytes', 'peak_rss_through_inference_bytes'):
            r.pop(k)
    changes = differences(*clean)
    assert changes.keys() <= {'/storage/sealed_slot_reads', '/cell_ownership/stats/marker_union_requests'}, changes
    files = ('state.json', 'stages.json', 'binding-audit.json') if audit else ('state.json',)
    hashes = {f: sha(root / lanes[0] / f) for f in files}
    assert all(sha(root / lanes[1] / f) == h for f, h in hashes.items())
    return dict(runs=len(reports[0]['steps']), hashes=hashes, changed_work=changes,
        matched_cells_completed=coverage, current_work_credit_delta=0,
        program_file_sha256=sha(program))


def collect(root, commit):
    result = compare(root, ('run-baseline', 'run-candidate'), root / 'sum/program.json')
    assert result['matched_cells_completed'] == 419
    previous = Path(__file__).with_name('closed-cells-check.json')
    assert sha(root / 'runtime-baseline') == load(previous)['binaries']['candidate']
    accepted = load(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass' and accepted['input_sha256']['cpu_values'] == result['hashes']['state.json']
    fixtures = {}
    for audit in (True, False):
        suffix = '' if audit else '-normal'
        records = load(root / f'fixture-runs{suffix}.json')
        expected = {(case, lane, bits) for case in ('matched', 'boundaries', 'legacy')
            for lane in ('baseline', 'candidate') for bits in (64, 0)}
        assert len(records) == len(expected) and {(r['case'], r['lane'], r['bits']) for r in records} == expected
        for r in records:
            folder = root / f'fixture-{r["case"]}'
            assert r['diagnostic_process_seconds'] < 1 and r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            assert r['runtime_sha256'] == sha(root / f'runtime-{r["lane"]}')
            assert r['program_sha256'] == sha(folder / 'program.json')
            assert r['argv'] == [str(root / f'runtime-{r["lane"]}'), '--program', str(folder / 'program.json'),
                '--output', str(folder / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence'] + (['--audit-stages'] if audit else [])
        for case in ('matched', 'boundaries', 'legacy'):
            folder = root / f'fixture-{case}'
            for bits in (64, 0):
                pair = compare(folder, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'), folder / 'program.json', audit)
                assert (pair['matched_cells_completed'] > 0) == (case != 'boundaries')
                fixtures[f'{case}-{bits}{suffix}'] = pair
    tests = {}
    for name, count in [('matched', 3), ('matched-all', 3), ('aliases', 3), ('aliases-all', 3),
            ('publications', 9), ('witness', 8), ('scoped', 12), ('credit', 4), ('barrier', 1), ('history', 1)]:
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, sha256=sha(path))
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    scoped = load(root / 'scoped-executor.json')
    assert not scoped['after_seed']['executor']['global_observer']
    assert scoped['after_b_consumption']['executor']['stats']['published_tables_while_pending'] > 0
    assert scoped['final_state_and_ordered_step_bindings_match']
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    baseline = load(root / 'run-baseline/report.json')
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0].keys() == metrics[1].keys()
    metric_changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert all(k.startswith(('report:/stats/matched_cells_completed ', 'report:/storage/sealed_slot_reads '))
        for k in metric_changes)
    result.update(scope='standalone Cell CPU; short work/semantic checks, no timing or allocator campaign',
        baseline_commit='808aadb3', candidate_commit=commit, semantic_acceptance='pass',
        previous_evidence_sha256=sha(previous), fixtures=fixtures, tests=tests,
        fixture_manifests={suffix: sha(root / f'fixture-runs{suffix}.json') for suffix in ('', '-normal')},
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        scoped_sha256=sha(root / 'scoped-executor.json'), relower_sha256=sha(root / 'relower.json'),
        relower_components=len(relower['components']), opportunity=load(root / 'opportunity.json'),
        unchanged_work_metrics=len(metrics[0]) - len(metric_changes), changed_work_metrics=metric_changes,
        removed_unused_registrations=dict(attempts=sum(baseline['multi_stage']['stats'][k]
            for k in ('complete_bindings', 'residual_bindings')),
            basis='One old BTreeSet insertion per admitted continuation, inferred from preserved binding counts; not allocator or Work credit'),
        limits='Matched completion replaces transient RHS preparation, not logical effects. The old avoided-frame counter already includes empty transient release. Source union queues, IDs, facts, Run order, real receipts and visibility remain authoritative. Compiled enum replaces one bool per rule; setup classification adds an alias-coverage scan. No measured time or allocation gain; minimal no-default build retains ordinary execution. General RHS selection, source marker materialization, Bake composition and final parallel acceptance remain incomplete.',
        timing_cadence=dict(last_timed_commit='808aadb3', implementation_commits_since_timing=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root.resolve(), args.commit), indent=2) + '\n')
