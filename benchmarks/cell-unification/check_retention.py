#!/usr/bin/env python3
"""Verify Cell-scoped result history against frozen execution; no timing runs."""
import argparse
import json
from pathlib import Path
import re

from check_context import RUN_KEYS
from check_links import load, sha, work
from check_view_query import stable

COUNTERS = ('history_allocations', 'history_slots_written')


def collect(root, commit):
    def pair(directory, lanes, program, files):
        reports = [load(directory / lane / 'report.json') for lane in lanes]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in reports)
        counts = {k: [r['stage_spine']['stats'][k] for r in reports] for k in COUNTERS}
        for before, after in counts.values():
            assert after <= before
        clean = [stable(work(r)) for r in reports]
        for r in clean:
            r['steps'] = [[s[k] for k in RUN_KEYS] for s in r['steps']]
            for k in ('peak_rss_through_setup_bytes', 'peak_rss_through_inference_bytes'):
                r.pop(k)
            for k in COUNTERS:
                r['stage_spine']['stats'].pop(k)
        assert clean[0] == clean[1], (directory, 'other work changed')
        hashes = {f: sha(directory / lanes[0] / f) for f in files}
        assert all(sha(directory / lanes[1] / f) == digest for f, digest in hashes.items())
        return dict(runs=len(reports[0]['steps']), ordered_hashes=hashes,
            program_sha256=sha(program), history_before_after=counts,
            handoff_deep=reports[1]['stats']['handoff_deep'])

    result = pair(root, ('run-baseline', 'run-candidate'), root / 'sum/program.json', ('state.json',))
    semantic = load(root / 'semantic-acceptance.json')
    assert semantic['status'] == 'pass'
    assert semantic['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1], 'sum-bits must preserve existing work'
    fixtures = {}
    for name in ('chain', 'retired'):
        path = root / f'fixture-{name}'
        program = path / 'program.json'
        assert load(program)['iterative_bake']['rhs_handoffs']['max_back'] == 2
        for bits in (64, 0):
            f = pair(path, (f'baseline-{bits}', f'candidate-{bits}'), program,
                ('state.json', 'stages.json', 'binding-audit.json'))
            assert f['handoff_deep'] > 0
            assert all(after < before for before, after in f['history_before_after'].values())
            fixtures[f'{name}-{bits}'] = f
    records = load(root / 'fixture-runs.json')
    assert {(r['case'], r['lane'], r['bits']) for r in records} == {
        (case, lane, bits) for case in ('chain', 'retired')
        for lane in ('baseline', 'candidate') for bits in (64, 0)}
    assert len(records) == 8
    for r in records:
        assert r['diagnostic_process_seconds'] < 1
        assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
        runtime = root / f'runtime-{r["lane"]}'
        fixture = root / f'fixture-{r["case"]}'
        program = fixture / 'program.json'
        assert r['argv'] == [str(runtime), '--program', str(program), '--output',
            str(fixture / f'{r["lane"]}-{r["bits"]}'), '--local-congruence', '--audit-stages']
        assert r['runtime_sha256'] == sha(runtime) and r['program_sha256'] == sha(program)
    tests = {}
    for name, count in (('history', 6), ('receipts', 7), ('witness', 8), ('deep', 1)):
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, log_sha256=sha(path))
    minimal = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in minimal.read_text()
    tests['minimal'] = dict(status='pass', log_sha256=sha(minimal))
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result.update(scope='standalone Cell CPU; normal release work checks; no timing or allocation campaign',
        baseline_commit='acab2911', candidate_commit=commit, semantic_acceptance='pass',
        unchanged_work_metrics=len(metrics[0]), fixtures=fixtures, tests=tests,
        fixture_runs_sha256=sha(root / 'fixture-runs.json'),
        relower=dict(components=len(relower['components']), sha256=sha(root / 'relower.json')),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        removed='Global catalog-depth retention at every completed Cell. Shared compiled transitions and actual query/RHS reads now determine each state\'s required history, including inherited jumps and default restarts. Bake rebuilds the retention bound with its current composition.',
        limits='History allocation counters count structural containers, not total allocator calls or bytes. Each switch state adds a retention word; deep saved frames now include the Trail enum tag. Fixed-point setup and storage changes are not timed. Current results remain available to ordinary witness readers; published sibling histories, visibility, deletion and Run offsets remain authoritative. No marker materialization or full Bake takeover claimed.',
        timing_cadence=dict(last_timed_commit='acab2911', implementation_commits_since_timing=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit), indent=2) + '\n')
