#!/usr/bin/env python3
"""Summarize the two saved wall-stack samples and the dispatch ablation."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import statistics
import sys


def profile(directory):
    parse = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads']
    raw = directory / 'stacks.txt'
    diagnostic = json.loads((directory / 'diagnostic.json').read_text())
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert digest == diagnostic['sample']['stacks_sha256']
    threads = parse(raw)
    waits = []
    stack = []
    thread = -1
    for line in raw.read_text().split('Call graph:\n', 1)[1].split('Total number in stack', 1)[0].splitlines():
        match = re.match(r'([ +!|:`]*)(\d+) (.*)', line)
        if not match:
            continue
        depth, count, symbol = len(match[1]), int(match[2]), match[3]
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack:
            thread += 1
            waits.append({})
        if symbol.startswith('__psynch_cvwait '):
            ancestry = ' '.join(s for _, s in stack)
            if thread:
                category = 'inside_job' if 'StackJob' in ancestry else 'pool_idle'
            elif 'apply_worker_writes' in ancestry or '::write_cells' in ancestry:
                category = 'scalar_rhs_writes'
            elif 'complete_local_births' in ancestry:
                category = 'synchronous_local_rhs'
            elif 'drain_cell_queue' in ancestry:
                category = 'ready_queue'
            elif 'finish_expansion_rules' in ancestry or 'query_workers' in ancestry:
                category = 'query'
            elif 'publish' in ancestry:
                category = 'publication'
            else:
                category = 'other'
            waits[thread][category] = waits[thread].get(category, 0) + count
        stack.append((depth, symbol))
    summary = []
    for data, categories in zip(threads, waits):
        count = data['inclusive'].get('__psynch_cvwait', 0)
        assert sum(categories.values()) == count
        summary.append({'samples': data['samples'], 'condition_wait_samples': count,
                        'condition_wait_fraction': count / data['samples'], 'contexts': categories})
    return {k: diagnostic[k] for k in (
        'runtime_sha256', 'program_file_sha256', 'state_sha256', 'schedule_sha256', 'runs', 'sample')} | {'threads': summary}


def collect(root):
    result = {'scope': 'standalone Cell CPU; wall-stack residence, not CPU utilization',
              'limits': 'Five-second partial windows, logging and sampling perturb execution. Inclusive frames overlap. Pool call timers include work and are not pure wait time.',
              'profiles': [profile(root / name) for name in ('wait-profile-1', 'wait-profile-2')]}
    samples = json.loads((root / 'dispatch-ablation/samples.json').read_text())
    result['dispatch_ablation'] = {}
    for lane, data in samples['lanes'].items():
        times = [s['inference_seconds'] for s in data['samples']]
        result['dispatch_ablation'][lane] = {
            'args': data['args'], 'runtime_sha256': data['runtime_sha256'],
            'program_file_sha256': data['program_file_sha256'],
            'inference_samples_seconds': times, 'inference_median_seconds': statistics.median(times),
            'state_hashes': sorted({s['state_sha256'] for s in data['samples']}),
            'schedule_hashes': sorted({s['schedule_sha256'] for s in data['samples']})}
    return result


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(collect(Path(sys.argv[1])), indent=2) + '\n')
