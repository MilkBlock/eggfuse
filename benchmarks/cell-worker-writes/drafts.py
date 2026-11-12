#!/usr/bin/env python3
"""Retain unsuccessful intermediate timings alongside the final candidate."""
import json
from pathlib import Path
import statistics
import sys


def collect(root):
    drafts = []
    for name, layout in (
        ('.', 'two phases, extra Instance array, fresh writer boxes'),
        ('accepted', 'borrowed Instance array, reused writer boxes, two phases'),
        ('direct', 'one pool call, saved Root Cursor container'),
        ('root', 'one pool call, deferred Root creation, boxed batch counters'),
    ):
        sample = json.loads((root / name / 'timing-ray/samples.json').read_text())
        assert sample.get('finished_at_utc') and 'failure' not in sample
        lanes = {}
        for lane, data in sample['lanes'].items():
            times = [s['inference_seconds'] for s in data['samples']]
            lanes[lane] = {
                'runtime_sha256': data['runtime_sha256'], 'args': data['args'],
                'program_file_sha256': data['program_file_sha256'],
                'inference_seconds': times, 'median_seconds': statistics.median(times),
                'state_hashes': sorted({s['state_sha256'] for s in data['samples']}),
                'schedule_hashes': sorted({s['schedule_sha256'] for s in data['samples']})}
        drafts.append({'directory': name, 'layout': layout, 'lanes': lanes})
    return {'scope': 'actual standalone Cell CPU; fresh processes, interleaved controls; not native egglog',
            'limits': 'Sequential development sessions with varying machine load. Compare lanes within each session; do not combine control medians across drafts.',
            'drafts': drafts}


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(collect(Path(sys.argv[1])), indent=2) + '\n')
