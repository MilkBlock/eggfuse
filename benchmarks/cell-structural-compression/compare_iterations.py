#!/usr/bin/env python3
"""Compare saved audited runtime iterations and their separate peak observers."""
import hashlib
import json
import pathlib
import sys

before, after, before_peak, after_peak, output = map(pathlib.Path, sys.argv[1:])
paths = (before, after, before_peak, after_peak)
a, b, ap, bp = [json.loads(p.read_text()) for p in paths]
if a['run_checks'] != b['run_checks']:
    raise SystemExit('Run graph or ordered effect audits differ')
for trace, peak in ((a, ap), (b, bp)):
    if trace['run_checks'][-1]['graph'] != peak['final_state_sha256'] or trace['runs'] != peak['runs']:
        raise SystemExit('peak observer differs from audited execution')
old = dict(a['field_release_compacted'])
new = dict(b['field_release_compacted'])
result = {
    'scope': 'actual standalone Cell runtime; Graph teardown and separate single-lane process requested-heap observer',
    'runs': b['runs'],
    'all_run_graph_and_ordered_audits_equal': True,
    'graph_heap_before': a['graph_owned_heap_requested_after'],
    'graph_heap_after': b['graph_owned_heap_requested_after'],
    'graph_heap_saved': a['graph_owned_heap_requested_after'] - b['graph_owned_heap_requested_after'],
    'changed_field_release_bytes': {k: {'before': old.get(k, 0), 'after': new.get(k, 0)}
                                   for k in sorted(old.keys() | new.keys()) if old.get(k, 0) != new.get(k, 0)},
    'process_peak_before': ap['execution_and_takeover_peak_bytes'],
    'process_peak_after': bp['execution_and_takeover_peak_bytes'],
    'initialization_relative_peak_growth_before': ap['net_growth_over_setup_bytes'],
    'initialization_relative_peak_growth_after': bp['net_growth_over_setup_bytes'],
    'takeover_extra_peak_before': ap['max_takeover_extra_bytes'],
    'takeover_extra_peak_after': bp['max_takeover_extra_bytes'],
    'limitation': 'process peaks and initialization-relative net growth are not Graph-exclusive peaks; field teardown charges shared allocations to last owner',
    'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
}
if 'maintenance' in ap and 'maintenance' in bp:
    result['maintenance'] = {'before': ap['maintenance'], 'after': bp['maintenance']}
output.write_text(json.dumps(result, indent=2) + '\n')
