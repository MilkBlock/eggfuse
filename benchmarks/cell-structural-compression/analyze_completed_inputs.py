#!/usr/bin/env python3
"""Compare audited completed-binding retirement with its prior execution."""
import json
import sys
from pathlib import Path


def analyze(before, after, old_heap, new_heap):
    for run in (before, after):
        if not run['all_saved_run_checks_equal']:
            raise ValueError('missing Run boundary acceptance')
    if before['final_state'] != after['final_state']:
        raise ValueError('final state changed')
    for heap in (old_heap, new_heap):
        if heap['mode'] != 'inherited-owners':
            raise ValueError('expected same inherited-owner mode')
        if heap['runs'] != after['runs'] or heap['program_sha256'] != after['program_sha256']:
            raise ValueError('heap measurement workload differs')
    if old_heap['final_state_sha256'] != new_heap['final_state_sha256']:
        raise ValueError('heap measurement final state changed')
    if before['program_sha256'] != after['program_sha256'] or before['runs'] != after['runs']:
        raise ValueError('audit workload differs')
    if before['measured_work'] != after['measured_work']:
        raise ValueError('execution work changed; investigate before claiming only storage removal')
    return {
        'scope': 'actual standalone Cell runtime, requested Graph heap; not native egglog, RSS or speedup',
        'program_sha256': after['program_sha256'], 'runs': after['runs'],
        'all_saved_run_checks_equal': True, 'final_state_exact_equal': True,
        'measured_execution_work_equal': True,
        'graph_heap_before': old_heap['graph_owned_teardown_bytes'],
        'graph_heap_after': new_heap['graph_owned_teardown_bytes'],
        'graph_heap_saved': old_heap['graph_owned_teardown_bytes'] - new_heap['graph_owned_teardown_bytes'],
        'program_heap_before': old_heap['retained_program_teardown_bytes'],
        'program_heap_after': new_heap['retained_program_teardown_bytes'],
        'process_peak_before': old_heap['execution_and_takeover_peak_bytes'],
        'process_peak_after': new_heap['execution_and_takeover_peak_bytes'],
        'transfer_extra_before': old_heap['max_takeover_extra_bytes'],
        'transfer_extra_after': new_heap['max_takeover_extra_bytes'],
        'explicit_slots_before': before['source_storage']['explicit_cell_slots'],
        'explicit_slots_after': after['source_storage']['explicit_cell_slots'],
        'graph_counter_changes': {k: [before['graph_work'].get(k), v] for k, v in after['graph_work'].items()
                                  if before['graph_work'].get(k) != v},
        'limitations': ['shared-prefix bindings remain unchanged',
                       'reclaiming removed-slot capacity can reallocate; no timing benefit established',
                       'no new rule, fact, index or RHS elimination established'],
    }


if __name__ == '__main__':
    if len(sys.argv) != 6:
        raise SystemExit('usage: analyze_completed_inputs.py OLD_AUDIT NEW_AUDIT OLD_HEAP NEW_HEAP OUTPUT')
    result = analyze(*(json.loads(Path(p).read_text()) for p in sys.argv[1:5]))
    Path(sys.argv[5]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
