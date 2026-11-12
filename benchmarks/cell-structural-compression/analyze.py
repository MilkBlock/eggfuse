#!/usr/bin/env python3
"""Review one saved runtime trace; never execute the workload or adjust acceptance."""
import collections
import hashlib
import json
import pathlib
import sys

base_path, final_path, output_path = map(pathlib.Path, sys.argv[1:])
base = json.loads(base_path.read_text())
final = json.loads(final_path.read_text())
if base['run_checks'] != final['run_checks']:
    raise SystemExit('original Run graph/ordered audit trace differs')
assert final['every_run_graph_and_ordered_audits_equal']
original = base['graph_owned_heap_requested_before']
retained = final['graph_owned_heap_requested_after']
layout = final['ownership']['inventory']['shared_field_layout_bytes']
origins = collections.Counter(f['origin']['cell'] for f in final['function_trace']
                              if f['live'] and f['origin'] is not None)
kinds = collections.Counter()
empty = collections.Counter()
templates = collections.defaultdict(lambda: collections.Counter())
for identity, cell in final['instance_trace']:
    values = cell['values']
    kinds.update(next(iter(v)) for v in values.values())
    row = templates[cell['template']]
    row.update(instances=1, slots=len(values), facts=len(cell['facts']))
    if not cell['facts']:
        empty.update(instances=1, slots=len(values), function_users=origins[identity])
result = {
    'scope': 'actual standalone Cell runtime, not native egglog; fixed original baseline',
    'program_sha256': base['program_sha256'],
    'original_graph_heap_bytes': original,
    'optimized_graph_heap_bytes': retained,
    'remaining_fraction': retained / original,
    'target_bytes': original * 3 // 10,
    'target_met_graph_heap': retained * 10 <= original * 3,
    'added_shared_field_layout_bytes': layout,
    'graph_plus_added_layout_fraction': (retained + layout) / original,
    'limitation': 'shared layout is charged separately; within-Run peak and complete Program/Executor heap are not measured',
    'runs': final['runs'],
    'all_original_run_graph_and_audit_digests_equal': True,
    'boundary_array_peak_before': final['boundary_peak_before'],
    'boundary_array_peak_after': final['boundary_peak_after'],
    'source_counts': final['compacted'],
    'ordered_field_releases': final['field_release_compacted'],
    'explicit_slot_types': dict(kinds),
    'fact_free_frames': dict(empty),
    'largest_retained_templates': [dict(template=t, **c) for t, c in
                                 sorted(templates.items(), key=lambda x: -x[1]['slots'])[:20]],
    'traces': {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (base_path, final_path)},
}
output_path.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['optimized_graph_heap_bytes', 'remaining_fraction',
      'added_shared_field_layout_bytes', 'target_met_graph_heap']}))
