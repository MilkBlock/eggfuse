#!/usr/bin/env python3
"""Replay a bounded receipt archive; never authorize execution from this output."""
import collections
import json
import sys
from pathlib import Path


def identity(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def follow(value, edges):
    path, seen = [], set()
    while identity(value) in edges:
        key = identity(value)
        if key in seen:
            raise ValueError('cyclic receipt forwarding archive')
        seen.add(key)
        edge = edges[key]
        path.append(edge)
        value = edge['to']
    return value, path


def analyze(run):
    archive = run['receipt_trace']
    if not run['all_saved_run_checks_equal']:
        raise ValueError('Run graph/effect checks did not pass')
    if archive['schema'] != 'cell-receipt-lifetime-trace/v1':
        raise ValueError('unsupported archive')
    trace = archive['trace']
    if not archive['complete_archive'] or trace['dropped']:
        raise ValueError('incomplete archive cannot establish a forwarding chain')
    historical, current, captures, refreshes, retires = {}, {}, collections.defaultdict(list), collections.defaultdict(list), {}
    counts, failures, clears = collections.Counter(), [], []
    previous_run = 0
    for index, row in enumerate(trace['events']):
        source_run, event = row['run'], row['event']
        if source_run < previous_run:
            raise ValueError('source Run order regressed')
        previous_run = source_run
        kind = event['kind']
        counts[kind] += 1
        if kind == 'forward':
            edge = {'index': index, 'run': source_run, **event}
            historical[identity(event['from'])] = edge
            current[identity(event['from'])] = edge
        elif kind == 'clear':
            if event['edges'] != len(current):
                raise ValueError('unobserved forwarding-map mutation')
            clears.append({'index': index, 'run': source_run, 'edges': len(current)})
            current.clear()
        elif kind == 'capture':
            captures[identity(event['witness'])].append({'index': index, 'run': source_run, 'rule': event['rule'], 'slot': event['slot']})
        elif kind == 'refresh':
            refreshes[identity(event['from'])].append({'index': index, 'run': source_run, **event})
        elif kind == 'retire':
            retires[identity(event['fact'])] = {'index': index, 'run': source_run, **event}
        elif kind == 'failure':
            original = event['original']
            resolved, _ = follow(original, current)
            target, path = follow(original, historical)
            if resolved != event['resolved'] or target != event['archived_target'] or len(path) != event['hops']:
                raise ValueError('observer and offline forwarding replay disagree')
            failures.append({
                'index': index, 'run': source_run, **event,
                'chain': path,
                'cleared_chain_edges': sum(any(c['index'] > e['index'] for c in clears) for e in path),
                'source_run_age': source_run - path[0]['run'] if path else None,
                'captures_of_original': list(captures[identity(original)]),
                'refreshes_of_original': list(refreshes[identity(original)]),
                'retirement_of_original': retires.get(identity(original)),
            })
        else:
            raise ValueError('unknown event kind: ' + kind)
    expected = run['stage_work']['ripsat_witness_fallbacks'] - run['stage_work']['ripsat_witness_missing']
    if len(failures) != expected:
        raise ValueError('failure archive does not match runtime counters')
    return {
        'scope': 'actual standalone Cell runtime; offline causal observation, not executable closure proof or speedup',
        'program_sha256': run['program_sha256'], 'runs': run['runs'],
        'all_saved_run_checks_equal': True, 'events': sum(counts.values()), 'dropped_events': trace['dropped'],
        'event_counts': dict(counts), 'failures': len(failures),
        'historical_target_visible_at_failure': sum(f['target_visible'] for f in failures),
        'historical_chain_crosses_clear': sum(f['cleared_chain_edges'] > 0 for f in failures),
        'historical_chain_crosses_source_run': sum((f['source_run_age'] or 0) > 0 for f in failures),
        'chain_hops': dict(sorted(collections.Counter(f['hops'] for f in failures).items())),
        'source_run_ages': dict(sorted(collections.Counter(f['source_run_age'] for f in failures if f['source_run_age'] is not None).items())),
        'failures_with_prior_refresh_of_same_receipt': sum(bool(f['refreshes_of_original']) for f in failures),
        'failures_with_capture_after_prior_refresh': sum(any(c['index'] > r['index'] for c in f['captures_of_original'] for r in f['refreshes_of_original']) for f in failures),
        'failure_sites': dict(collections.Counter(f"{f['rule']}:{identity(f['site'])}:{f['table']}" for f in failures)),
        'details': failures,
        'limitations': ['capture/refresh events identify receipts and logical sites, not unique shared storage owners',
                        'only forwarding created while ordinary receipt tracking is enabled is archived',
                        'visibility is sampled at failure; it does not authorize early RHS publication',
                        'the archive is not a proposed persistent runtime forwarding index'],
    }


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: analyze_receipt_lifetime.py AUDITED_TRACE OUTPUT')
    result = analyze(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('details', 'limitations')}))
