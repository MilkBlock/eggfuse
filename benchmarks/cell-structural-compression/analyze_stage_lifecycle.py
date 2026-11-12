"""Bound stage-shared lifecycle savings from live Cell facts, without rerunning."""
import collections
import json
import sys
from pathlib import Path


def analyze(data):
    trace = data['source_storage']['fact_lifecycle']
    frames = {f['cell']: f for f in trace['frames']}
    membership = {}
    for component in data['ownership_storage']['components']:
        for cell in component['frames']:
            assert cell not in membership
            membership[cell] = component['id']
    # No ownership evidence: do not combine unrelated singleton frames.
    groups = collections.defaultdict(list)
    for cell, frame in frames.items():
        owner = ('component', membership[cell]) if cell in membership else ('source', cell)
        groups[owner].append(frame)
    totals = collections.Counter()
    opportunities = []
    for owner, group in groups.items():
        live = [(f, s) for f in group for s in f['facts']]
        if not live:
            continue
        # Keep all lifecycle flags in the grouping. Entry references and hashes
        # are not eliminated or credited; their facts retain distinct identities.
        cohorts = collections.Counter((s['epoch'], s['born'], s['hidden'],
                                        s['owned'], s['local_union_owned']) for _, s in live)
        per_frame = sum(len({(s['epoch'], s['born'], s['hidden'], s['owned'],
                             s['local_union_owned']) for s in f['facts']}) for f in group)
        all_completed = all(f['completed'] for f in group)
        pair_bytes = trace['epoch_pair_bytes']
        gross = (len(live) - len(cohorts)) * pair_bytes
        extra_cross_frame = (per_frame - len(cohorts)) * pair_bytes
        totals['facts'] += len(live)
        totals['facts_with_epoch_different_from_birth'] += sum(s['epoch'] != s['born'] for _, s in live)
        totals['frames_with_mixed_fact_epochs'] += sum(len({s['epoch'] for s in f['facts']}) > 1 for f in group)
        totals['frames_with_mixed_fact_births'] += sum(len({s['born'] for s in f['facts']}) > 1 for f in group)
        totals['cohorts'] += len(cohorts)
        totals['epoch_pair_gross_upper_bound_bytes'] += gross
        totals['cross_frame_extra_gross_upper_bound_bytes'] += extra_cross_frame
        if all_completed:
            totals['completed_epoch_pair_gross_upper_bound_bytes'] += gross
        if len(group) > 1:
            totals['multi_frame_owners'] += 1
        opportunities.append({'owner': list(owner), 'frames': len(group), 'facts': len(live),
            'cohorts': len(cohorts), 'all_completed': all_completed,
            'cross_stage': len({f['started_epoch'] for f in group}) > 1,
            'epoch_pair_gross_upper_bound_bytes': gross,
            'cross_frame_extra_gross_upper_bound_bytes': extra_cross_frame,
            'entry_facts': sum(s['entry'] is not None for _, s in live),
            'decoded_facts': sum(s['decoded'] for _, s in live),
            'templates': sorted({f['template'] for f in group})})
    graph = data['graph_owned_teardown_bytes']
    return {'program_sha256': data['program_sha256'], 'runs': data['runs'],
        'scope': 'live standalone Cell runtime snapshot, not a proof of transition invariance',
        'graph_owned_teardown_bytes': graph, 'totals': dict(totals),
        'epoch_pair_gross_upper_bound_fraction_of_graph': totals['epoch_pair_gross_upper_bound_bytes']/graph,
        'largest_groups': sorted(opportunities, key=lambda x: -x['epoch_pair_gross_upper_bound_bytes'])[:30],
        'obligations': ['No net savings claimed: cohort IDs, exceptions, split/update costs are uncharged.',
            'Later union, hide, refresh and retirement can split a cohort; final equality is not a proof.',
            'Fact identities, hashes, Entry witnesses, residual enumeration and Run visibility remain live.',
            'Cross-frame savings are a subset of total savings, never additive.',
            'Missing or incomplete frames cannot establish saturated closure.']}


if __name__ == '__main__':
    source, output = map(Path, sys.argv[1:])
    result = analyze(json.loads(source.read_text()))
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['totals'], sort_keys=True))
