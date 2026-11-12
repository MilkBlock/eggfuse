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
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print('Every timing sample, warmup, runtime, state, Run summary and quiet profile verified')
