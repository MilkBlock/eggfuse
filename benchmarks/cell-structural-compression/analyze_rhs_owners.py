#!/usr/bin/env python3
"""Before-effect owner snapshots; no inferred ancestry or maintained runtime map."""
import collections
import json
import sys
from pathlib import Path
from analyze_rhs_before import analyze as validate


def same(a, b):
    return a is not None and b is not None and a['component'] == b['component']


def analyze(audit):
    validate(audit)
    counts = collections.Counter()
    patterns = collections.Counter()
    accessible = set()
    by_cell = collections.defaultdict(list)
    for b in audit['rhs_projection_trace']['trace']['boundaries']:
        by_cell[b['cell']].append(b)
    for b in audit['rhs_projection_trace']['trace']['boundaries']:
        if b['prior_status'] != 'visible': continue
        if 'prior_receipt' not in b or 'owner_links' not in b:
            raise ValueError('missing pre-boundary ownership observation')
        if b['prior_receipt'] is None: raise ValueError('visible predecessor lacks receipt')
        cross = b['previous_run'] != b['run']
        prefix = 'cross_run' if cross else 'same_run'
        counts[prefix + ':visible'] += 1
        counts[prefix + ':same_returned_receipt'] += b['prior_receipt'] == b['receipt']
        links = b['owner_links']
        if links is None:
            counts[prefix + ':ownership_unavailable'] += 1
            continue
        donor = links['donor']
        counts[prefix + ':donor_has_component'] += donor is not None
        counts[prefix + ':receiver_has_component'] += links['receiver'] is not None
        counts[prefix + ':entry_present'] += links['entry_present']
        counts[prefix + ':query_witnesses'] += len(links['query'])
        counts[prefix + ':query_atoms'] += links['query_atoms']
        sources = [('receiver', None, links['receiver'])]
        sources += [('entry', a['atom'], a['location']) for a in links['anchors']]
        sources += [('query', a['atom'], a['location']) for a in links['query']]
        if links['parent']:
            sources.append(('parent', None, links['parent']['location']))
        reachable = [(kind, atom, loc) for kind, atom, loc in sources if same(loc, donor)]
        counts[prefix + (':same_component_source' if reachable else ':no_observed_same_component_source')] += 1
        if reachable:
            accessible.add((b['cell'], b['operation']))
            kind, atom, source = reachable[0]
            fact = b['prior_receipt'].get('Fact')
            if fact is None: raise ValueError('component donor is not a fact')
            patterns[(b['rule'], b['operation'], kind, atom, source['shape'],
                      source['ordinal'], donor['ordinal'], fact['op'])] += 1
    complete = collections.Counter()
    complete_rules = collections.Counter()
    trace = audit['rhs_projection_trace']['trace']
    for e in trace['events']:
        rows = by_cell[e['cell']]
        sites = trace['plans'][e['rule']]['constructor_sites']
        if (len(rows) != sites or len({b['operation'] for b in rows}) != sites
                or not all(b['success'] and (b['cell'], b['operation']) in accessible for b in rows)):
            continue
        cross = any(b['previous_run'] != b['run'] for b in rows)
        complete['cells'] += 1
        complete['constructor_requests'] += e['constructor_requests']
        complete['cross_run_cells'] += cross
        complete['cross_run_constructor_requests'] += e['constructor_requests'] if cross else 0
        complete_rules[e['rule']] += 1
    return dict(scope='actual standalone runtime pre-boundary component reachability; not key equality or saturation proof',
        program_sha256=audit['program_sha256'], counts=dict(counts),
        complete_cells=dict(complete), complete_rules=dict(complete_rules),
        patterns=[dict(rule=k[0], operation=k[1], source_kind=k[2], atom=k[3], shape=k[4],
                       source_ordinal=k[5], donor_ordinal=k[6], donor_operation=k[7], observations=n)
                  for k,n in patterns.most_common()],
        obligations=[
            'Component IDs compare only within each pre-boundary snapshot.',
            'Same component supplies an addressing opportunity, not a full-key equivalence proof.',
            'Query snapshots contain only already retained witnesses; missing ones remain unknown.',
            'No matching demands, reverse subscriptions, result ownership or execution behavior are changed.',
            'Coverage, residual matches, source Run order and lifecycle checks still govern takeover.'
        ])


if __name__ == '__main__':
    current = json.loads(Path(sys.argv[1]).read_text())
    result = analyze(current)
    if len(sys.argv) == 4:
        baseline = json.loads(Path(sys.argv[3]).read_text())
        for k in ('program_sha256', 'runs', 'final_state', 'graph_work', 'source_storage'):
            if current[k] != baseline[k]: raise ValueError('observation changes ' + k)
        result['baseline_state_graph_work_storage_equal'] = True
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts'], indent=2))
