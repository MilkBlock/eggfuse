#!/usr/bin/env python3
"""Actual pre-boundary receipt liveness, not a runtime cache or skip proof."""
import collections
import json
import sys
from pathlib import Path


def analyze(run):
    archive = run['rhs_projection_trace']
    trace = archive['trace']
    if (not run['all_saved_run_checks_equal'] or not archive['complete_archive']
            or trace['dropped'] or trace['boundary_dropped']):
        raise ValueError('incomplete or unvalidated trace')
    totals = collections.Counter()
    rules = collections.defaultdict(collections.Counter)
    for e in trace['boundaries']:
        if e['prior_status'] not in ('unobserved', 'receipt_not_retained', 'retired', 'wrong_table', 'hidden', 'visible'):
            raise ValueError('unknown receipt state')
        if (e['previous_run'] is None) != (e['prior_status'] == 'unobserved'):
            raise ValueError('missing predecessor identity')
        if e['previous_run'] is not None and e['previous_run'] > e['run']:
            raise ValueError('predecessor from future Run')
        kind = ('first' if e['previous_run'] is None else
                'cross_run' if e['previous_run'] != e['run'] else 'same_run')
        for c in (totals, rules[e['rule']]):
            c['observations'] += 1
            c[kind] += 1
            c[kind + ':' + e['prior_status']] += 1
            c['actual_new_facts'] += e['facts']
            c['missing_returned_receipts'] += e['receipt'] is None
            if e['prior_status'] == 'visible':
                c['visible_prior_new_facts'] += e['facts']
                c['visible_prior_failed'] += not e['success']
                c['visible_prior_forwarded'] += e['forwarded']
    by_cell = collections.defaultdict(list)
    routes = collections.Counter()
    for e in trace['boundaries']:
        by_cell[e['cell']].append(e)
        if e['prior_status'] == 'visible' and e['previous_run'] != e['run']:
            routes[(e['previous_rule'], e['rule'])] += 1
    complete = collections.Counter()
    complete_rules = collections.defaultdict(collections.Counter)
    for e in trace.get('events', []):
        boundaries = by_cell[e['cell']]
        sites = trace['plans'][e['rule']]['constructor_sites']
        if (len(boundaries) != sites or len({b['operation'] for b in boundaries}) != sites
                or not all(b['prior_status'] == 'visible' and b['success'] for b in boundaries)):
            continue
        cross = any(b['previous_run'] != b['run'] for b in boundaries)
        for c in (complete, complete_rules[e['rule']]):
            c['cells'] += 1
            c['cross_run_cells'] += cross
            c['constructor_requests'] += e['constructor_requests']
            c['cross_run_constructor_requests'] += e['constructor_requests'] if cross else 0
            c['new_facts'] += e['facts']
            c['updates'] += e['updates']
            c['union_requests'] += e['union_requests']
    return {'scope': 'actual standalone Cell runtime; before constructor boundary execution',
            'runs': run['runs'], 'all_saved_run_checks_equal': True,
            'counts': dict(totals),
            'all_constructor_boundaries_previously_visible': dict(complete),
            'complete_rules': {str(r): dict(c) for r, c in sorted(complete_rules.items())},
            'cross_run_visible_routes': [dict(producer=a, consumer=b, boundaries=n)
                                         for (a, b), n in routes.most_common()],
            'rules': {str(r): dict(c) for r, c in sorted(rules.items())},
            'limitations': [
                'Only generic constructor boundaries of pure constructor templates are sampled.',
                'Prepared/local-birth operations and direct completions are not covered.',
                'Diagnostic map is bounded, owns no Cells, and is never used by execution.',
                'Keys are not re-canonicalized after unions; this undercounts candidates.',
                'Visibility is checked before execution using actual returned receipts, not producer addresses.',
                'Each site is checked when reached, not simultaneously at Cell entry.',
                'This does not discharge publication, delta ownership, query matching or retained history.',
                'No memory or latency reduction is established by this observer.']}

if __name__ == '__main__':
    current = json.loads(Path(sys.argv[1]).read_text())
    result = analyze(current)
    if len(sys.argv) == 4:
        baseline = json.loads(Path(sys.argv[3]).read_text())
        for key in ('program_sha256', 'runs', 'final_state', 'graph_work', 'source_storage'):
            if current[key] != baseline[key]: raise ValueError('observer changes ' + key)
        result['baseline_state_graph_work_storage_equal'] = True
        result['observation_read_changes'] = {k: [baseline['measured_work'].get(k), v]
            for k, v in current['measured_work'].items() if baseline['measured_work'].get(k) != v}
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))
