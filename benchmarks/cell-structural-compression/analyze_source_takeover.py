#!/usr/bin/env python3
"""Inventory surviving source state and bounded histories from saved executions."""
import collections
import hashlib
import json
import sys
from pathlib import Path

paths = list(map(Path, sys.argv[1:]))
if len(paths) not in (5, 6):
    raise SystemExit("usage: analyze_source_takeover.py TRACE PEAK SHORT_PROFILE LONG_PROFILE OUTPUT [SEEDED_PROFILE]")
trace_path, peak_path, short_path, long_path, output_path = paths[:5]
trace, peak, short, long = [json.loads(p.read_text()) for p in
                           (trace_path, peak_path, short_path, long_path)]
if trace['run_checks'][-1]['graph'] != peak['final_state_sha256']:
    raise SystemExit('source trace and ownership snapshot differ')
cells = dict(trace['instance_trace'])
components = peak['ownership_storage']['components']
groups = collections.Counter()
values = collections.Counter()
duplicate = collections.Counter()
in_component = set()
for component in components:
    live = [i for i in component['frames'] if i in cells]
    in_component.update(live)
    groups[f"{len(component['frames'])} addresses / {len(live)} source records"] += 1
    seen = set()
    for cell in live:
        for value in cells[cell]['values'].values():
            kind = next(iter(value))
            key = json.dumps(value, sort_keys=True)
            values[kind] += 1
            duplicate[kind] += key in seen
            seen.add(key)

def histories(profile):
    lengths = collections.Counter()
    repeated = collections.Counter()
    for row in profile['records']:
        length = len(row['fragment']['hops']) + 1
        lengths[length] += 1
        if row['observed']['activations'] >= 2:
            repeated[length] += 1
    return {'limit': profile.get('max_frames', 4), 'candidates': len(profile['records']),
            'candidate_frame_lengths': dict(sorted(lengths.items())),
            'repeated_candidate_frame_lengths': dict(sorted(repeated.items()))}

stats = trace['ownership']['stats']
result = {
    'scope': 'actual standalone Cell runtime; offline evidence, no source retirement or memory saving claimed',
    'source_records': len(cells),
    'empty_value_sources': sum(not c['values'] for c in cells.values()),
    'fact_free_sources': sum(not c['facts'] for c in cells.values()),
    'source_records_inside_components': len(in_component),
    'component_frame_and_source_record_counts': dict(sorted(groups.items())),
    'explicit_values_inside_components': dict(values),
    'repeated_raw_values_inside_components': dict(duplicate),
    'warning': 'Raw value equality is not a static proof; overlaps do not measure reclaimable storage. Facts, readers and deleted-producer lifetimes remain authoritative.',
    'existing_composition_requests': stats['composition_requests'],
    'existing_capacity_cuts': stats['composition_capacity_cuts'],
    'existing_unbaked_fallbacks': stats['composition_unbaked_fallbacks'],
    'short_history': histories(short), 'long_history': histories(long),
    'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     (trace_path, peak_path)},
    'profile_sha256': {'short': hashlib.sha256(short_path.read_bytes()).hexdigest(),
                      'long': hashlib.sha256(long_path.read_bytes()).hexdigest()},
}
if len(paths) == 6:
    seeded = json.loads(paths[5].read_text())
    result['seeded_history'] = histories(seeded)
    result['seeded_history']['seed_catalog'] = seeded['seed_catalog']
    result['profile_sha256']['seeded'] = hashlib.sha256(paths[5].read_bytes()).hexdigest()
output_path.write_text(json.dumps(result, indent=2) + '\n')
