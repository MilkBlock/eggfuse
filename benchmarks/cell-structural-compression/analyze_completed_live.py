#!/usr/bin/env python3
"""Compare completed-state retirement, keeping full heap and slot subsets separate."""
import json
import sys
from pathlib import Path

before, after, old_heap, new_heap = [json.loads(Path(p).read_text()) for p in sys.argv[1:5]]
for k in ('program_sha256', 'runs', 'final_state'):
    if before[k] != after[k]: raise ValueError('changed ' + k)
if not after['all_saved_run_checks_equal']: raise ValueError('Run checks failed')
allowed = {'completed_dead_slots_elided', 'completed_dead_frames_compacted'}
changed = {k: [before['graph_work'].get(k), v] for k,v in after['graph_work'].items()
           if before['graph_work'].get(k) != v}
if set(changed) - allowed: raise ValueError('unexpected execution change: ' + str(changed))
for k in ('program_sha256', 'runs', 'mode', 'final_state_sha256'):
    if old_heap[k] != new_heap[k]: raise ValueError('heap lane differs: ' + k)
if old_heap['program_sha256'] != after['program_sha256']: raise ValueError('heap program differs')
source_keys = ('explicit_cell_slots','cell_slot_bytes','writer_bytes','parent_links','completed_owner_frames','cell_fact_arities')
heap_keys = ('graph_owned_teardown_bytes','retained_program_teardown_bytes','execution_and_takeover_peak_bytes','net_growth_over_setup_bytes','max_takeover_extra_bytes')
result = dict(scope='actual standalone Cell runtime; requested heap, not RSS or native egglog',
    program_sha256=after['program_sha256'], runs=after['runs'], all_saved_run_checks_equal=True,
    source_storage={k: [before['source_storage'][k], after['source_storage'][k]] for k in source_keys},
    graph_work_changes=changed, heap={k: [old_heap[k],new_heap[k]] for k in heap_keys},
    net_graph_and_program_saved_bytes=sum(old_heap[k]-new_heap[k] for k in heap_keys[:2]),
    limitations=['No decrease in facts, source frame count, RHS requests or maintenance work.',
                 'Cross-stage reads retain actual result aliases and lazy Copy dependencies.',
                 'Program discard layouts increase; they are charged against Graph savings.',
                 'Parent detachment is proven in a regression; workload parent links remain unchanged.'])
Path(sys.argv[5]).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result,indent=2))
