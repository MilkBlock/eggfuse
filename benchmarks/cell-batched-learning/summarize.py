"""Summarize per-input runtime storage and exact same-source Run checks."""
import json
import sys
from pathlib import Path
from pool import canonical

root, output = map(Path, sys.argv[1:])
def read(path):
    return json.loads((root/path).read_text())
manifest, selection, profile = read('manifest.json'), read('shared-selection.json'), read('pooled-profile.json')
chosen = {canonical(f) for f in selection['fragments']}
selected_records = [r for r in profile['records'] if canonical(r['fragment']) in chosen]
rows = []
for case in manifest['cases']:
    name = case['case']
    b, a, check = [read(f'{name}/{file}.json') for file in ['baseline-heap','candidate-heap','verification']]
    assert check['run_graph_rhs_writes_equal'] is True
    assert check['baseline'] == b['program_sha256'] and check['candidate'] == a['program_sha256']
    assert a['final_state_sha256'] == b['final_state_sha256'] == check['final_state'] == case['final_state']
    assert a['runs'] == b['runs'] == check['runs']
    copied=read(f'{name}/candidate-copied-directory-heap.json')
    assert copied['program_sha256']==a['program_sha256']
    assert copied['final_state_sha256']==a['final_state_sha256']
    assert copied['retained_program_teardown_bytes']==a['retained_program_teardown_bytes']
    assert {k:v for k,v in copied['graph_fields'] if k!='ownership.transitions'} == {k:v for k,v in a['graph_fields'] if k!='ownership.transitions'}
    before, after = b['graph_owned_teardown_bytes'], a['graph_owned_teardown_bytes']
    fields = dict(b['graph_fields'])
    rows.append(dict(case=name, source_sha256=case['source_sha256'], runs=check['runs'],
        baseline_program=b['program_sha256'], candidate_program=a['program_sha256'],
        graph_bytes_before=before, graph_bytes_after=after, graph_delta=after-before,
        graph_bytes_with_copied_catalog=copied['graph_owned_teardown_bytes'],
        duplicate_directory_bytes_removed=copied['graph_owned_teardown_bytes']-after,
        graph_reduction_fraction=1-after/before,
        retained_program_bytes_before=b['retained_program_teardown_bytes'],
        retained_program_bytes_after=a['retained_program_teardown_bytes'],
        source_frames_before=b['source_storage']['completed_owners']['source_records']+b['source_storage']['completed_owner_frames'],
        source_frames_after=a['source_storage']['completed_owners']['source_records']+a['source_storage']['completed_owner_frames'],
        explicit_slots_before=b['source_storage']['explicit_cell_slots'],
        explicit_slots_after=a['source_storage']['explicit_cell_slots'],
        fact_bytes_before=b['source_storage']['fact_record_live_bytes'],
        fact_bytes_after=a['source_storage']['fact_record_live_bytes'],
        changed_graph_fields={k:v-fields.get(k,0) for k,v in a['graph_fields'] if v!=fields.get(k,0)},
        run_graph_rhs_writes_equal=True,
        selected_paths_seen_in_training=sum(name in r['samples'] for r in selected_records),
        selected_paths_from_other_inputs=sum(name not in r['samples'] for r in selected_records)))
before, after = sum(r['graph_bytes_before'] for r in rows), sum(r['graph_bytes_after'] for r in rows)
result = dict(scope='four separate standalone Cell executions sharing one learned catalog; no timing or native semantic claim',
    pool=read('pool-summary.json'), selected_fragments=len(chosen),
    selected_shared_across_inputs=sum(len(r['samples'])>1 for r in selected_records),
    cases=rows, aggregate=dict(graph_bytes_before=before,graph_bytes_after=after,
        graph_reduction_fraction=1-after/before,
        meaning='sum of separate final Graph heaps, not a combined live egraph or a peak'),
    admission='all four Graph heaps improve after eliminating duplicate directory; no held-out or native-generalization claim',
    limitations=['Same-source Run checks do not extend the native semantic contract beyond reviewed sum-bits.',
                 'This unmarked direct-source batch differs from the prior marked sum-bits baseline.',
                 'All four inputs contribute training data; these are not held-out generalization results.',
                 'Static definition identity is conservative; this is not saturation-history equivalence.'])
output.write_text(json.dumps(result,indent=2)+'\n')
