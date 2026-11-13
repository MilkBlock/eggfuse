"""Account for child storage reuse without conflating it with compression."""
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
rows = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    d = root/name
    before = json.loads((d/'candidate-residual-parent-heap.json').read_text())
    after = json.loads((d/'candidate-nested-owner-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    metrics = {}
    for label, data in [('before',before),('after',after)]:
        counts=data['completion_work']
        metrics[label] = dict(graph_bytes=data['graph_owned_teardown_bytes'],
            takeover_temporary_peak=data['max_takeover_extra_bytes'],
            source_records=data['source_storage']['completed_owners']['source_records'],
            completed_frames=data['source_storage']['completed_owners']['completed_frames'],
            owners=data['source_storage']['completed_owners']['owners'],
            moved_old_slots=counts['shared_owner_slot_entries_moved'],
            moved_old_facts=counts['shared_owner_fact_entries_moved'])
    rows.append(dict(case=name,source_program=after['program_sha256'],**metrics,
                     graph_bytes_added=metrics['after']['graph_bytes']-metrics['before']['graph_bytes'],
                     segment_extensions=after['completion_work']['shared_owner_segment_extensions'],
                     reused_segments=after['completion_work']['shared_owner_segments_reused'],
                     same_final_state=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='actual standalone Cell runtime; optional segment reuse; no speed or compression claim',
    admission='not selected: all four final Graph heaps increase',cases=rows),indent=2)+'\n')
