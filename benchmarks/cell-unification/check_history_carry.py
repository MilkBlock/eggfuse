#!/usr/bin/env python3
"""Validate saved internal Cell history transfers; never run a timing campaign."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha
from check_alias_routes import same_execution, clean
from check_mixed_outputs import differences


def compare(root, lanes, program, audit=False):
    directories = [root / lane for lane in lanes]
    result = same_execution(directories, [program, program], audit)
    reports = [load(d / 'report.json') for d in directories]
    carried = reports[1]['stage_spine']['stats']['history_carried_steps']
    handle = reports[1]['stage_spine']['history_handle_bytes']
    assert handle == 16
    values = list(map(clean, reports))
    # These two metrics are new. Missing baseline instrumentation is not zero.
    for r in values:
        r['stage_spine'].pop('history_handle_bytes', None)
        r['stage_spine']['stats'].pop('history_carried_steps', None)
    changed = differences(*values)
    assert changed.keys() <= {'/stage_spine/stats/history_allocations', '/stage_spine/stats/history_slots_written'}, changed
    result.update(changed_work=changed, carried_steps=carried, history_handle_bytes=handle,
        program_file_sha256=sha(program), reports_sha256=[sha(d / 'report.json') for d in directories])
    return result


def collect(root, commit):
    result = compare(root, ('run-baseline', 'run-candidate'), root / 'sum/program.json')
    assert result['changed_work'] == {} and result['carried_steps'] == 0
    previous = Path(__file__).with_name('alias-routes-check.json')
    assert sha(root / 'runtime-baseline') == load(previous)['binaries']['candidate']
    semantic = load(root / 'semantic-acceptance.json')
    assert semantic['status'] == 'pass' and semantic['input_sha256']['cpu_values'] == result['hashes']['state.json']
    fixtures = {}
    for audit in (True, False):
        suffix = '' if audit else '-normal'
        records = load(root / f'fixture-runs{suffix}.json')
        expected = {(c, l, b) for c in ('chain', 'retired') for l in ('baseline', 'candidate') for b in (64, 0)}
        assert len(records) == len(expected) and {(r['case'], r['lane'], r['bits']) for r in records} == expected
        for r in records:
            folder = root / f'fixture-{r["case"]}'
            assert r['diagnostic_process_seconds'] < 1
            assert r['runtime_sha256'] == sha(root / f'runtime-{r["lane"]}')
            assert r['program_sha256'] == sha(folder / 'program.json')
            assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            assert r['argv'] == [str(root / f'runtime-{r["lane"]}'), '--program', str(folder / 'program.json'),
                '--output', str(folder / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence'] + (['--audit-stages'] if audit else [])
        for case in ('chain', 'retired'):
            folder = root / f'fixture-{case}'
            for bits in (64, 0):
                pair = compare(folder, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'), folder / 'program.json', audit)
                assert pair['carried_steps'] == 2
                assert pair['changed_work'] == {'/stage_spine/stats/history_allocations': [6, 2],
                    '/stage_spine/stats/history_slots_written': [8, 4]}
                fixtures[f'{case}-{bits}{suffix}'] = pair
    tests = {}
    for name, count in [('history', 8), ('witness', 11), ('query', 7), ('matched', 3), ('switch', 1)]:
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, sha256=sha(path))
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    credits = {}
    for record in load(root / 'credit-manifest.json'):
        argv = record['argv']
        assert record['binary_sha256'] == sha(Path(argv[0]))
        assert record['reports_sha256'] == [sha(Path(p)) for p in argv[1:3]]
        v = load(Path(argv[3]))
        credits[record['case']] = dict(net_saved_operations=v['net_saved_operations'],
            changed_counters={k: c for k, c in v['counters'].items() if c['saved']})
    assert {k: v['net_saved_operations'] for k, v in credits.items()} == {'sum': 0, 'chain': 8, 'retired': 8}
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items() if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0].keys() == metrics[1].keys()
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert all(k.startswith(('report:/stage_spine/history_handle_bytes ', 'report:/stage_spine/stats/history_carried_steps ')) for k in changes), changes
    result.update(scope='standalone Cell CPU; short semantic/work checks, not native egglog or a timing/allocator campaign',
        candidate_commit=commit, baseline_commit='c2f665a2', semantic_acceptance='pass', fixtures=fixtures, tests=tests,
        work_credit=credits, binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        unchanged_work_metrics=len(metrics[0])-len(changes), changed_work_metrics=changes,
        opportunity=load(root / 'opportunity.json'),
        representation_cost='History handle grows from one pointer (8 bytes in baseline source) to 16 bytes with an empty-stage offset; entries inside a deep history remain pointer-sized. Slot reads now adjust that offset. No total allocator or speed claim.',
        limits='Removes result-history transfer at intermediate Cells without new exports. A stage may still execute graph effects; original Run/publication boundaries and ordinary witness validation remain. Nonempty result-frame transfers and generic Entry publication are not removed. Sum-bits does not exercise this takeover.',
        timing_cadence=dict(last_timed_commit='c2f665a2', implementation_commits_since_timing=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root.resolve(), args.commit), indent=2) + '\n')
