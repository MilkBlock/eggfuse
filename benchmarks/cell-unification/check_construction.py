#!/usr/bin/env python3
"""Verify shared Cell constructor-result propagation and native marker emission."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS, GROUPS
from check_view_query import stable


def collect(root, commit, phase='construction', timed=False):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    groups = (*GROUPS, 'publication', 'entry_schedule', 'view_consumers', 'view_storage', 'known_results')
    def pair(directory, lanes, program, files):
        a, b = [load(directory / lane / 'report.json') for lane in lanes]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in (a, b))
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in groups: assert stable(work(a[group])) == stable(work(b[group])), (directory, group)
        hashes = {f: sha(directory / lanes[0] / f) for f in files}
        assert all(sha(directory / lanes[1] / f) == digest for f, digest in hashes.items())
        return dict(runs=len(a['steps']), ordered_hashes=hashes, program_file_sha256=sha(program),
            known_results=stable(work(b['known_results'])))
    result = pair(root, ('run-baseline', 'run-candidate'), root / 'sum/program.json', ('state.json',))
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1]
    fixtures = {}
    for name in ('handoff', {'symbols': 'union', 'bindings': 'bindings', 'candidates': 'bindings'}.get(phase, 'computed')):
        path = root / f'fixture-{name}'
        for bits in (64, 0):
            f = pair(path, (f'baseline-{bits}', f'candidate-{bits}'), path / 'compiled/program.json',
                ('state.json', 'stages.json', 'binding-audit.json'))
            fixtures[f'{name}-{bits}'] = f
    runs = load(root / 'fixture-runs.json')
    assert len(runs) == 8 and all(r['diagnostic_process_seconds'] < 1 for r in runs)
    for r in runs:
        assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
        assert r['runtime_sha256'] == sha(root / f'runtime-{r["lane"]}')
        assert r['program_sha256'] == sha(root / f'fixture-{r["case"]}/compiled/program.json')
    tests = {}
    expected = (('symbols', 1), ('symbols-nonsparse', 1), ('closure', 1), ('marker', 6), ('barrier', 1), ('committed', 1)) if phase == 'symbols' else (
        ('construction', 1), ('construction-nonsparse', 1), ('cell', 2), ('marker', 6), ('witness', 8))
    if phase == 'bindings':
        expected = (('cell', 14), ('binding-nonsparse', 1), ('marker', 7), ('witness', 8))
    elif phase == 'candidates':
        expected = (('cell', 15), ('binding-nonsparse', 2), ('marker', 7), ('witness', 8))
    for name, count in expected:
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, log_sha256=sha(path))
    minimal = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in minimal.read_text()
    tests['minimal'] = dict(status='pass', log_sha256=sha(minimal))
    emissions = load(root / 'compiler-compare.json')
    assert len(emissions) == 2
    for row in emissions:
        fixture = root / f'fixture-{row["case"]}'
        assert row['source_sha256'] == sha(fixture / 'source.egg')
        assert set(row['unchanged_files']) == {'source_sk_mk.egg', 'marker-selection.json', 'marker-program.json', 'program.json'}
        for name, digest in row['unchanged_files'].items():
            assert digest == sha(fixture / 'compiled' / name) == sha(fixture / 'compiled-baseline' / name)
        for lane, digest in row['compiler_sha256'].items(): assert digest == sha(root / f'compiler-{lane}')
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result.update(scope='standalone Cell CPU; normal release; no timing or allocation campaign', baseline_commit='f6e44667',
        candidate_commit=commit, semantic_acceptance='pass', unchanged_report_groups=groups,
        unchanged_work_metric_values_or_missing_status=len(metrics[0]), fixtures=fixtures,
        fixture_runs_sha256=sha(root / 'fixture-runs.json'), tests=tests,
        marker_emission=emissions,
        relower=dict(components=len(relower['components']), sha256=sha(root / 'relower.json')),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        removed='Separate marker constructor-result memo/selection and typed static source propagation; standalone resolve_alias entrypoint. Both frontends use the Cell construction flow for first-witness preservation, ordered fresh construction and reuse. The typed frontend also uses its Copy propagation and table invalidation.',
        limits='This is compile-time propagation over existing query/effect operands, not a runtime fact graph. Native lexical bindings, purity/deletion admission and typed SSA/deletion policy remain host obligations. Marker selection, iterative materialization boundaries and general Bake composition are not yet unified. The 5853 sum-bits static eliminations were already present and are preserved, not new savings. New operand keys and temporary proof-state layout have not been allocation/timing-profiled.',
        timing_cadence=dict(last_timed_commit='cc472d0f', implementation_commits_since_timing=2))
    if phase == 'symbols':
        result.update(baseline_commit='46aa864b',
            removed='Independent marker union-find and congruence key/fixed-point loop. Marker publication and typed cross-stage handoffs now execute Cell Symbols; source operands are resolved once instead of repeatedly rendering terms and looking up child IDs during closure and row projection.',
            limits='The source adapter retains expressions only for .egg emission and caches child symbols during compilation. Source publication admission, matching, materialization selection and iterative boundary composition remain separate. Source effects become equality evidence only at the publication boundary; typed queued unions keep their original barriers. Generic source-name keys and cached operand storage have not been timing/allocation-profiled; no new runtime credit or repair takeover is claimed.',
            timing_cadence=dict(last_timed_commit='cc472d0f', implementation_commits_since_timing=3))
    elif phase == 'bindings':
        result.update(baseline_commit='08c6b90b',
            removed='Independent field-binding logic in runtime queries, typed producer-local projections, and source marker publication. Arg is the typed Cell Operand alias; all three use Cell Bindings and bind_operand. Marker fields are lowered once per proof, eliminating candidate-loop JSON dispatch, literal term lookup and owned variable-name copies.',
            limits='Runtime bindings remain in the existing query/Entry frame. Static projections require exact typed operands; source symbols require equality at their publication boundary; runtime literals use the repaired graph. These distinct evidence obligations are preserved. Candidate enumeration, materialization selection and iterative boundary composition are not yet unified. The temporary source pattern and generic binder have not been allocation/timing-profiled; unchanged counters do not establish speed preservation.',
            timing_cadence=dict(last_timed_commit='cc472d0f', implementation_commits_since_timing=4))
    elif phase == 'candidates':
        result.update(baseline_commit='c54780d8',
            removed='Independent source/typed local candidate projection loops and temporary uniqueness maps/sets. Cell project_rows preserves source identity alongside original bindings, and unique_projection retains the first equivalent candidate and stops at ambiguity. Typed operator filtering precedes frame cloning; source root enumeration keeps deterministic deduplication.',
            limits='Source publication uniqueness is by binding, typed donor uniqueness is by source row; the shared implementation preserves both obligations. Equality evidence, donor admission, global fragment discovery/selection, runtime candidate directories and iterative materialization boundaries remain separate. Deleted static scans, frame clones and temporary collections are not allocation counts or runtime credit.',
            timing_cadence=dict(last_timed_commit=commit if timed else 'cc472d0f', implementation_commits_since_timing=0 if timed else 5,
                implementation_commits_in_batch=['f6e44667','46aa864b','08c6b90b','c54780d8',commit]))
    if timed:
        assert phase == 'candidates'
        from collect_sieve import timing
        result['scope'] = 'standalone Cell CPU; normal release timing; not native egglog runtime; allocations not collected'
        result['timing'] = timing(root, commit, commits=dict(baseline='c54780d8', candidate=commit,
            last_timed='cc472d0f', historical='24c4ae8a'))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--phase', choices=('construction', 'symbols', 'bindings', 'candidates'), default='construction')
    p.add_argument('--timing', action='store_true')
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit, args.phase, args.timing), indent=2) + '\n')
