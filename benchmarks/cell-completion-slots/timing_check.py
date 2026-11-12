#!/usr/bin/env python3
"""Reuse the existing complete timing gate for the next five-change checkpoint."""
import json
from pathlib import Path
import runpy
import sys


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    root = Path(sys.argv[1])
    checker = runpy.run_path(str(Path(__file__).parents[1] / 'cell-write-completion/timing_check.py'))
    result = checker['collect'](root, revisions=json.loads((root / 'runtime-revisions.json').read_text()),
                                evidence_path=Path(__file__).with_name('results.json'))
    observations = [json.loads(line) for line in (root / 'background-samples.jsonl').read_text().splitlines()]
    result['background_sampling'] = {
        'sha256': checker['sha'](root / 'background-samples.jsonl'),
        'interval_seconds': 5,
        'samples': len(observations),
        'compiler_samples': [r for r in observations if r['compiler_processes']],
        'limits': 'Separate process snapshots; CPU values are OS lifetime averages, not inference-only utilization. They cannot exclude shorter unsampled background work.',
    }
    result['four_worker_direction_checks'] = {}
    for prior in ('historical', 'control', 'checkpoint'):
        comparisons = {case: result['workloads'][case]['candidate_comparisons'][prior]['4']
                       for case in ('sum', 'ray')}
        medians = all(c['median_change_percent'] < 0 for c in comparisons.values())
        pairs = all(c['paired_median_change_percent'] < 0 for c in comparisons.values())
        result['four_worker_direction_checks'][prior] = {
            'both_workload_medians_lower': medians,
            'both_workload_paired_medians_lower': pairs,
            'direction': 'consistent' if medians and pairs else 'mixed',
            'limits': 'Directional summary, not a significance test or an automatic speedup acceptance. Semantic checks do not establish performance.',
        }
    # These are the saved actual work executions, not an additional timing
    # run or a claim to isolate dispatch time from the full RHS phase.
    old_path = Path(__file__).parents[1] / 'cell-root-births/results.json'
    old = json.loads(old_path.read_text())
    current = json.loads(Path(__file__).with_name('results.json').read_text())
    assert old['control_commit'] == result['runtime_revisions']['checkpoint']
    assert old['control_runtime_sha256'] == result['workloads']['ray']['lanes']['checkpoint4']['runtime_sha256']
    growth = {'checkpoint_work_evidence_sha256': checker['sha'](old_path),
              'scope': 'Saved standalone CPU work executions with the same programs; not isolated synchronization timing',
              'workloads': {}}
    for case in ('sum', 'ray'):
        a, b = old['workloads'][case], current['workloads'][case]
        for key in ('state_sha256', 'schedule_sha256', 'runs', 'program_sha256', 'logical_effects'):
            assert a[key] == b[key], (case, key)
        growth['workloads'][case] = {}
        for name, work in (('checkpoint', a['work']['control']), ('candidate', b['work']['candidate'])):
            growth['workloads'][case][name] = {
                'key_lookup_calls': work['key_lookup_calls'], 'source_frames': work['frames'],
                'scheduler': {k: work['scheduler'][k] for k in ('jobs', 'batches', 'queue_bytes', 'event_bytes', 'admission_waves')},
                'births': {k: work['births'][k] for k in ('local_births', 'worker_operations', 'root_jobs', 'root_bucket_probes', 'root_bucket_fallbacks')},
            }
    result['dispatch_growth_since_checkpoint'] = growth
    result['failed_profile_exports'] = []
    for suffix in ('disk-failure', 'disk-retry-failure'):
        log = root / f'profile-candidate4-{suffix}/runtime.log'
        if not log.exists():
            continue
        assert 'No space left on device' in log.read_text()
        result['failed_profile_exports'].append({'path': str(log), 'sha256': checker['sha'](log),
            'excluded': True, 'reason': 'Diagnostic export failed with ENOSPC; not a timing sample or semantic acceptance'})
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print('Every timing sample, warmup, runtime, state, Run summary and quiet profile verified')
