#!/usr/bin/env python3
"""Verify shared table-scoped read publication without running a timing campaign."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS, GROUPS
from check_view_query import stable


def collect(root, commit):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    groups = (*GROUPS, 'publication', 'entry_schedule', 'view_consumers', 'view_storage')
    def pair(directory, lanes, program, files):
        a, b = [load(directory / lane / 'report.json') for lane in lanes]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in (a, b))
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in groups: assert stable(work(a[group])) == stable(work(b[group])), (directory, group)
        hashes = {f: sha(directory / lanes[0] / f) for f in files}
        assert all(sha(directory / lanes[1] / f) == digest for f, digest in hashes.items())
        return dict(runs=len(a['steps']), ordered_hashes=hashes, program_file_sha256=sha(program),
            publication=b['publication'], neighbor_publication=b['neighbor_context']['publication'], range_work=b['physical']['range'])
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
    for name in ('neighbor', 'range'):
        path = root / f'fixture-{name}'
        for bits in (64, 0):
            f = pair(path, (f'baseline-{bits}', f'candidate-{bits}'), path / 'compiled/program.json',
                ('state.json', 'stages.json', 'binding-audit.json'))
            if name == 'neighbor': assert f['neighbor_publication']['refreshed'] > 0 and f['neighbor_publication']['retired'] > 0
            else: assert f['range_work']['uses'] > 0 and f['range_work']['update_rows'] > 0
            fixtures[f'{name}-{bits}'] = f
    runs = load(root / 'fixture-runs.json')
    assert len(runs) == 8 and all(r['diagnostic_process_seconds'] < 1 for r in runs)
    for r in runs:
        assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
        assert r['runtime_sha256'] == sha(root / f'runtime-{r["lane"]}')
        assert r['program_sha256'] == sha(root / f'fixture-{r["case"]}/compiled/program.json')
    tests = {}
    for name, count in (('neighbor-unit', 2), ('neighbor-nonsparse', 2), ('neighbor', 1), ('view', 1), ('scoped', 1)):
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, log_sha256=sha(path))
    minimal = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in minimal.read_text()
    tests['minimal'] = dict(status='pass', log_sha256=sha(minimal))
    scoped = load(root / 'scoped-executor.json')
    assert not scoped['after_seed']['executor']['global_observer']
    assert scoped['after_b_consumption']['executor']['stats']['published_tables_while_pending'] > 0
    assert scoped['final_state_and_ordered_step_bindings_match']
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result.update(scope='standalone Cell CPU; normal release; no timing or allocation campaign', baseline_commit='cc472d0f',
        candidate_commit=commit, semantic_acceptance='pass', unchanged_report_groups=groups,
        unchanged_work_metric_values_or_missing_status=len(metrics[0]), fixtures=fixtures,
        fixture_runs_sha256=sha(root / 'fixture-runs.json'), tests=tests,
        scoped_executor=dict(source_sha256=sha(root / 'scoped-executor.json'), global_observer=False,
            published_tables_while_pending=scoped['after_b_consumption']['executor']['stats']['published_tables_while_pending'],
            final_state_and_ordered_step_bindings_match=True),
        relower=dict(components=len(relower['components']), sha256=sha(root / 'relower.json')),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        removed='Neighbor subscribed-table vector/global version sweep and per-row Context lookup; range per-row table lookup/version writes. Columns, ranges and neighbor reads borrow table writers from the same repaired ChangeBatch and finish delivered tables only.',
        limits='Current/old witness identity, same-key replacement, negative reads, axes and candidate groups remain necessary. No reverse-key maps or row work were claimed removed. Counters do not measure deleted subscriber scans, table lookups or version stores; unchanged work metrics are not a speed proof. New unit coverage exercises selective batches and shared row delivery in sparse/nonsparse builds; no multithread acceptance.',
        timing_cadence=dict(last_timed_commit='cc472d0f', implementation_commits_since_timing=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit), indent=2) + '\n')
