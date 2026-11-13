"""Account for matched handoffs without treating hits as net compression."""
import json
import sys
from pathlib import Path


def summarize(audit, baseline_heap, candidate_heap):
    assert audit['baseline_saved_checks_equal'] and audit['graph_rhs_writes_equal']
    assert audit['runs'] == baseline_heap['runs'] == candidate_heap['runs']
    assert audit['base_program'] == baseline_heap['program_sha256']
    assert audit['program_sha256'] == candidate_heap['program_sha256']
    assert baseline_heap['final_state_sha256'] == candidate_heap['final_state_sha256']
    metrics = {}
    paths = [
        'key_lookup_calls', 'graph_work.constructor_requests', 'graph_work.handoff_lets',
        'graph_work.cells_created', 'graph_work.logical_facts_created',
        'stage.stats.matched_entry_resumptions', 'stage.stats.matched_entry_fields',
        'stage.stats.history_allocations', 'stage.stats.history_capture_reads',
        'stage.stats.cell_output_registrations', 'stage.stats.absorbed_root_completions',
        'stage.published_history_storage.owners',
        'stage.published_history_storage.owner_payload_bytes',
        'stage.published_history_storage.rc_header_bytes',
    ]
    def get(root, path):
        for part in path.split('.'):
            root = root[part]
        return root
    for path in paths:
        b, a = (get(audit[side], path) for side in ('before', 'after'))
        metrics[path] = {'before': b, 'after': a, 'delta': a-b}
    for key in ('graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
                'net_growth_over_setup_bytes', 'execution_and_takeover_peak_bytes'):
        b, a = baseline_heap[key], candidate_heap[key]
        metrics[key] = {'before': b, 'after': a, 'delta': a-b}
    return dict(scope='actual standalone Cell runtime, sum-bits; no timing claim',
                base_program=audit['base_program'], program_sha256=audit['program_sha256'],
                runs=audit['runs'], graph_rhs_writes_equal=True,
                resume_changed_runs=len(audit['resume_changed_runs']), metrics=metrics,
                compression_accepted=False,
                reason='Graph unchanged; additional retained history and execution growth. Program shrinkage is not egraph compression.')


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: analyze_matched_handoffs.py AUDIT BASE_HEAP CANDIDATE_HEAP OUTPUT')
    result = summarize(*(json.loads(Path(p).read_text()) for p in sys.argv[1:4]))
    Path(sys.argv[4]).write_text(json.dumps(result, indent=2) + '\n')
