#!/usr/bin/env python3
"""Check the Cell pair takeover, saved semantics and one five-commit timing campaign."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS, GROUPS
from collect_sieve import timing


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if not k.endswith('_s')}
    return [stable(v) for v in value] if isinstance(value, list) else value


def collect(root, commit, timed=False):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    groups = (*GROUPS, 'view_consumers', 'view_storage')
    def pair(directory, lanes, program, files):
        reports = [load(directory / lane / 'report.json') for lane in lanes]
        a, b = reports
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in reports)
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in groups: assert stable(work(a[group])) == stable(work(b[group])), (directory, group)
        hashes = {f: sha(directory / lanes[0] / f) for f in files}
        assert all(sha(directory / lanes[1] / f) == digest for f, digest in hashes.items())
        return dict(runs=len(a['steps']), ordered_hashes=hashes, program_file_sha256=sha(program),
                    view_work=b['view_consumers'])
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
    for name in ('dispatch', 'overlap', 'reversed', 'guards'):
        path = root / f'fixture-{name}'
        program = path / 'compiled/program.json'
        blocks = load(program)['view_consumer_blocks']
        assert len(blocks) == 1
        assert bool(blocks[0]['consumers']['dispatch']) == (name in ('dispatch', 'reversed'))
        for bits in (64, 0):
            fixtures[f'{name}-{bits}'] = pair(path, (f'baseline-{bits}', f'candidate-{bits}'), program,
                ('state.json', 'stages.json', 'binding-audit.json'))
            assert all(g['counts']['outputs'] > 0 for g in fixtures[f'{name}-{bits}']['view_work']['groups'])
    records = load(root / 'fixture-runs.json')
    assert len(records) == 16 and all(r['diagnostic_process_seconds'] < 1 for r in records)
    for r in records:
        assert r['runtime_sha256'] == sha(root / f'runtime-{r["lane"]}')
        assert r['program_sha256'] == sha(root / f'fixture-{r["case"]}/compiled/program.json')
    tests = {}
    for name, count in (('query', 4), ('view', 1), ('context', 1)):
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, log_sha256=sha(path))
    minimal = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in minimal.read_text()
    tests['minimal'] = dict(status='pass', log_sha256=sha(minimal))
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result.update(scope='standalone Cell CPU; not native egglog runtime', baseline_commit='f9cea51c',
        candidate_commit=commit, semantic_acceptance='pass', unchanged_report_groups=groups,
        unchanged_work_metric_values_or_missing_status=len(metrics[0]),
        fixtures=fixtures, fixture_runs_sha256=sha(root / 'fixture-runs.json'), tests=tests,
        relower=dict(components=len(relower['components']), sha256=sha(root / 'relower.json')),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        removed='Retained view Port/Test/Comparison operands and scalar interpreter; independent output binding map. Wire compatibility derives from the shared Cell Query and borrowed source input slots.',
        limits='Dedicated candidate directories, publication/retirement and original Run watermarks remain live. Three-way dispatch is derived from the shared query. Unit guards fold successful results without a runtime frame. Shared Query metadata and generic scalar binding costs are not separately allocation/instruction-counted. Unchanged metrics do not prove speed or full B3/Bake takeover.',
        timing_cadence=dict(last_timed_commit=commit if timed else 'f1c69507', implementation_commits_since_timing=0 if timed else 5,
            implementation_commits_in_batch=['3bd9d21e', 'c4e74d7c', 'fdc9179c', 'f9cea51c', commit]))
    if timed:
        result['timing'] = timing(root, commit, commits=dict(baseline='f9cea51c', candidate=commit,
            last_timed='f1c69507', historical='24c4ae8a'))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--timing', action='store_true')
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit, args.timing), indent=2) + '\n')
