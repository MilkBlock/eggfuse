#!/usr/bin/env python3
"""Apply the existing full timing/profile gate to this implementation checkpoint."""
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
        'sha256': checker['sha'](root / 'background-samples.jsonl'), 'interval_seconds': 5,
        'samples': len(observations), 'compiler_samples': [r for r in observations if r['compiler_processes']],
        'limits': 'OS lifetime CPU averages and periodic process snapshots, not inference-only utilization; shorter unsampled work is possible.',
    }
    result['four_worker_direction_checks'] = {}
    for prior in ('historical', 'checkpoint', 'control'):
        comparisons = [result['workloads'][case]['candidate_comparisons'][prior]['4'] for case in ('sum', 'ray')]
        faster = all(c['median_change_percent'] < 0 and c['paired_median_change_percent'] < 0 for c in comparisons)
        slower = all(c['median_change_percent'] > 0 and c['paired_median_change_percent'] > 0 for c in comparisons)
        result['four_worker_direction_checks'][prior] = {
            'direction': 'improved' if faster else 'regressed' if slower else 'mixed',
            'limits': 'Median and paired-median direction across both workloads; not a significance test.',
        }
    result['speedup_over_current_control'] = {
        'admitted': result['four_worker_direction_checks']['control']['direction'] == 'improved',
        'requirement': 'Both workload medians and iteration-paired medians must decrease against the current control.',
        'limits': 'Passing this directional gate would still not establish statistical significance or full thread utilization.',
    }
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print('All timing samples, warmups, state/Run checks and quiet profiles verified')
