#!/usr/bin/env python3
"""Analyze saved real owners; observed equality is not a reusable Bake proof."""
import collections
import hashlib
import json
import pathlib
import sys

trace_path, prior_path, output_path = map(pathlib.Path, sys.argv[1:])
trace = json.loads(trace_path.read_text())
prior = json.loads(prior_path.read_text())
if trace['final_state_sha256'] != prior['run_checks'][-1]['graph'] or trace['runs'] != prior['runs']:
    raise SystemExit('ownership trace differs from audited final graph')
x = trace['ownership_storage']
sources = {r['cell']: r for r in x['source_eq_bindings']}
counts, sizes, slots = collections.Counter(), collections.Counter(), collections.Counter()
templates = collections.defaultdict(collections.Counter)
for component in x['components']:
    roots = {r for r in component['roots'] if r is not None}
    counts['bound_symbols'] += sum(r is not None for r in component['roots'])
    counts['distinct_roots_summed_per_component'] += len(roots)
    sizes[len(component['frames'])] += 1
    for ordinal, cell in enumerate(component['frames']):
        counts['composition_frames'] += 1
        if cell not in sources:
            counts['composition_frames_without_physical_source_cell'] += 1
            continue
        source = sources[cell]
        program = x['programs'][x['shapes'][component['shape']]['programs'][ordinal]]
        for slot, raw, root in source['slots']:
            mapped = program['slots'][slot] is not None
            category = '{}_{}_{}'.format('completed' if source['completed'] else 'initial',
                'mapped' if mapped else 'unmapped', 'root_in_component' if root in roots else 'root_outside_component')
            slots[category] += 1
            templates[source['template']][category] += 1
counts['source_eq_slots_total'] = sum(len(s['slots']) for s in sources.values())
counts['source_eq_slots_outside_live_composition_frames'] = counts['source_eq_slots_total'] - sum(slots.values())
result = {
    'scope': 'saved actual final Cell runtime owners, not simulated compression or static coverage',
    'runs': trace['runs'],
    'final_graph_matches_audited_trace': True,
    'counts': dict(counts),
    'component_frame_histogram': dict(sorted(sizes.items())),
    'source_eq_slot_categories': dict(sorted(slots.items())),
    'templates': {str(k): dict(v) for k, v in sorted(templates.items())},
    'limitation': 'root membership does not prove the mapped local symbol has that value or that a reusable template can forward it; no savings credited',
    'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (trace_path, prior_path)},
}
output_path.write_text(json.dumps(result, indent=2) + '\n')
