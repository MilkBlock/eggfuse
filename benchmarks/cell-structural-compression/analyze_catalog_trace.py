#!/usr/bin/env python3
"""Analyze passive proposals against the exact installed catalog and saved state."""
import collections
import hashlib
import json
import sys
from pathlib import Path

prior_path, snapshot_path, observed_path, output_path = map(Path, sys.argv[1:])
prior, snapshot, observed = [json.loads(p.read_text()) for p in (prior_path, snapshot_path, observed_path)]
trace = observed['catalog_trace']
if trace['catalog_sha256'] != snapshot['program_sha256']:
    raise SystemExit('different installed catalog')
if observed['source_storage'] != prior['compacted'] or observed['ownership']['inventory'] != prior['ownership']['inventory']:
    raise SystemExit('observation changed retained source state or component inventory')
if not observed['all_saved_run_checks_equal'] or observed['runs'] != prior['runs']:
    raise SystemExit('missing Run acceptance')
owned = snapshot['ownership_storage']
pairs = set()
for fragment in owned['fragments']:
    if len(fragment['hops']) == 1:
        hop = fragment['hops'][0]
        pairs.add((fragment['root'], hop['rule'], hop['entry'], hop['op']))
groups = collections.defaultdict(collections.Counter)
lengths = collections.Counter()
for row in trace['records']:
    hop = row['fragment']['hops'][-1]
    source = owned['shapes'][row['source_shape']]['programs'][hop['source_frame']]
    kind = 'existing_local_pair' if (source, hop['rule'], hop['entry'], hop['op']) in pairs else 'new_local_pair'
    groups[kind]['candidates'] += 1
    groups[kind]['repeated_candidates'] += row['matched_births'] >= 2
    groups[kind]['birth_observations_overlapping'] += row['matched_births']
    lengths[len(row['fragment']['hops']) + 1] += 1
result = {
    'scope': 'actual standalone Cell runtime; passive observation, not an admitted optimization',
    'runs': observed['runs'], 'all_saved_run_checks_equal': True,
    'retained_source_census_unchanged': True, 'component_inventory_unchanged': True,
    'catalog': {k: trace[k] for k in ('catalog_sha256', 'executed_max_frames', 'max_frames', 'seed_shapes', 'seed_transitions', 'uncovered_births')},
    'proposal_count': len(trace['records']), 'proposal_frame_lengths': dict(sorted(lengths.items())),
    'candidate_classes': {k: dict(v) for k, v in sorted(groups.items())},
    'production_compositions_before_after': [prior['ownership']['stats']['composition_requests'], observed['ownership']['stats']['composition_requests']],
    'runtime_shape_builds': observed['ownership']['stats']['composition_shape_builds'],
    'limitation': 'Candidates overlap; available inputs are proposed reuse, not saved fields or bytes. Tracing visits formerly inactive Entries, so probe/capacity counters can increase without altering choices. No new compression result is claimed.',
    'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (prior_path, snapshot_path, observed_path)},
}
output_path.write_text(json.dumps(result, indent=2) + '\n')
