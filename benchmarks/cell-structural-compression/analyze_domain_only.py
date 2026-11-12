#!/usr/bin/env python3
"""Charge the memory/query-work tradeoff of replacing birth hints with Cell domains."""
import json
import sys
from pathlib import Path


def analyze(old, new, old_heap, new_heap):
    for run in (old, new):
        if not run['all_saved_run_checks_equal']:
            raise ValueError('Run acceptance missing')
        if run['program_sha256'] != old['program_sha256'] or run['runs'] != old['runs']:
            raise ValueError('audit workload differs')
    if old['final_state'] != new['final_state']:
        raise ValueError('final state changed')
    for heap in (old_heap, new_heap):
        if heap['mode'] != 'inherited-owners' or heap['program_sha256'] != old['program_sha256'] or heap['runs'] != old['runs']:
            raise ValueError('heap workload/configuration differs')
    if old_heap['final_state_sha256'] != new_heap['final_state_sha256']:
        raise ValueError('heap final state differs')
    old_ports = old_heap.get('port_index', old_heap.get('stable_fields'))
    ports = new_heap.get('port_index', new_heap.get('stable_fields'))
    if ports['birth_hints_enabled'] or ports['birth_indexed_port_keys'] != 0:
        raise ValueError('port birth index was not removed')
    for key in ('constructor_requests', 'constructor_reused', 'logical_facts_created', 'function_updates', 'unions'):
        if old['graph_work'][key] != new['graph_work'][key]:
            raise ValueError('mutation work changed: ' + key)
    fields_old, fields_new = dict(old_heap['graph_fields']), dict(new_heap['graph_fields'])
    keys = ('key_lookups', 'key_candidates', 'birth_hint_probes', 'birth_hint_hits', 'port_domain_probes')
    return {
        'scope': 'actual standalone Cell runtime; optional compression mode, no speedup claim',
        'program_sha256': new['program_sha256'], 'runs': new['runs'],
        'all_saved_run_checks_equal': True, 'final_state_equal': True,
        'graph_heap_before': old_heap['graph_owned_teardown_bytes'],
        'graph_heap_after': new_heap['graph_owned_teardown_bytes'],
        'graph_heap_saved': old_heap['graph_owned_teardown_bytes'] - new_heap['graph_owned_teardown_bytes'],
        'program_heap_before': old_heap['retained_program_teardown_bytes'],
        'program_heap_after': new_heap['retained_program_teardown_bytes'],
        'process_peak_before': old_heap['execution_and_takeover_peak_bytes'],
        'process_peak_after': new_heap['execution_and_takeover_peak_bytes'],
        'field_changes': {k: [v, fields_new[k]] for k, v in fields_old.items() if v != fields_new[k]},
        'indexed_port_keys_before': old_ports['birth_indexed_port_keys'],
        'indexed_port_keys_after': ports['birth_indexed_port_keys'],
        'port_query_work': {k: [old_ports['stats'][k], ports['stats'][k]] for k in keys},
        'measured_work_changes': {k: [old['measured_work'].get(k), v] for k, v in new['measured_work'].items()
                                  if old['measured_work'].get(k) != v},
        'limitations': ['complete port coverage is required; uncovered canonical indexes remain',
                       'facts and RHS mutations are unchanged',
                       'extra candidate/domain work is real; no timing improvement established',
                       'birth hash computation itself has not been eliminated'],
    }


if __name__ == '__main__':
    if len(sys.argv) != 6:
        raise SystemExit('usage: analyze_domain_only.py OLD_AUDIT NEW_AUDIT OLD_HEAP NEW_HEAP OUTPUT')
    result = analyze(*(json.loads(Path(p).read_text()) for p in sys.argv[1:5]))
    Path(sys.argv[5]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'measured_work_changes'}))
