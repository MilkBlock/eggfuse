"""Account for proven Entry value specialization against the current catalog."""
import json
import sys
from pathlib import Path
from collections import Counter


def summarize(audit, base, candidate):
    assert audit['source_specialization_verified']
    assert audit['baseline_saved_checks_equal'] and audit['graph_rhs_writes_equal']
    assert audit['runs'] == base['runs'] == candidate['runs']
    assert audit['base_program'] == base['program_sha256']
    assert audit['program_sha256'] == candidate['program_sha256']
    assert base['final_state_sha256'] == candidate['final_state_sha256']
    metrics = {}
    def pair(name, b, a):
        metrics[name] = dict(before=b, after=a, delta=a-b)
    for group, keys in {
        'graph_work': ['constructor_requests', 'decoded_rows', 'cells_created',
                       'logical_facts_created', 'completed_dead_slots_elided'],
        'source_storage': ['explicit_cell_slots', 'cell_slot_bytes', 'parent_links'],
    }.items():
        for key in keys:
            pair(group+'.'+key, audit['before'][group][key], audit['after'][group][key])
    pair('key_lookup_calls', audit['before']['key_lookup_calls'], audit['after']['key_lookup_calls'])
    for key in ['history_allocations', 'history_capture_reads']:
        pair('stage.'+key, audit['before']['stage']['stats'][key], audit['after']['stage']['stats'][key])
    for key in ['graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
                'net_growth_over_setup_bytes', 'execution_and_takeover_peak_bytes']:
        pair(key, base[key], candidate[key])
    def bindings(heap):
        c = Counter()
        for row in heap['ownership_storage']['source_eq_bindings']:
            c[row['template']] += len(row['slots'])
        return c
    b, a = bindings(base), bindings(candidate)
    return dict(scope='actual standalone Cell runtime; no timing claim',
                base_program=audit['base_program'], program_sha256=audit['program_sha256'],
                runs=audit['runs'], source_specialization_verified=True,
                graph_rhs_writes_equal=True, resume_changed_runs=len(audit['resume_changed_runs']),
                metrics=metrics,
                binding_changes=[dict(template=k, before=b[k], after=a[k])
                                 for k in sorted(b.keys() | a.keys()) if b[k] != a[k]],
                large_egraph_compression_proven=False)


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: analyze_entry_values.py AUDIT BASE_HEAP CANDIDATE_HEAP OUTPUT')
    result = summarize(*(json.loads(Path(p).read_text()) for p in sys.argv[1:4]))
    Path(sys.argv[4]).write_text(json.dumps(result, indent=2)+'\n')
