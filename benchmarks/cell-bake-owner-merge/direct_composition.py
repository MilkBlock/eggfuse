"""Audit one saved direct-source trace and its batched ownership selections."""
import collections
import hashlib
import json
import pathlib
import sys


def summarize(root, baseline_path, program_path):
    read = lambda p: json.loads(p.read_text())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    baseline, program = read(baseline_path), read(program_path)
    checked, observed = read(root / 'checked.json'), read(root / 'trace.json')
    trace, history = observed['catalog_trace'], observed['completed_history']
    if (checked['program_sha256'] != program['sha256']
            or baseline['program_sha256'] != program['sha256']
            or trace['catalog_sha256'] != program['sha256']
            or history['program_sha256'] != program['sha256']
            or not checked['every_run_graph_and_ordered_audits_equal']
            or not observed['all_saved_run_checks_equal']
            or len(checked['run_checks']) != observed['runs']
            or observed['final_state'] != checked['final_state']
            or history['dropped_events']):
        raise ValueError('source-bound complete audited observation required')
    depths, cross_run = [], 0
    for i, event in enumerate(history['events']):
        parent = event['parent']
        if parent is not None and not 0 <= parent < i:
            raise ValueError('noncausal history')
        depths.append(1 if parent is None else depths[parent] + 1)
        cross_run += parent is not None and event['run'] != history['events'][parent]['run']
    saturation = collections.Counter()
    for row in trace['saturation']['rows']:
        saturation[row['outcome']] += row['counts']['applications']
    multi = trace['multi_source']
    if multi['dropped_patterns'] or multi['inconsistent_slots']:
        raise ValueError('incomplete multi-source observation')
    widths = collections.Counter()
    for row in multi['patterns']:
        widths[len(row['pattern']['components'])] += row['counts']['applications']
    if sum(widths.values()) + multi['disconnected_entries'] != multi['multi_component_entries']:
        raise ValueError('unaccounted multi-source matches')
    candidates = {}
    for budget in (32, 128, 256):
        directory = root / f'budget{budget}'
        memory, raw = read(directory / 'memory.json'), read(directory / 'program.json')
        if (raw['source_core'] != program['source_core'] or raw['recipe'] != program['recipe']
                or memory['program_sha256'] != raw['sha256']
                or memory['final_state_sha256'] != baseline['final_state_sha256']
                or read(directory / 'state.json') != checked['final_state']):
            raise ValueError('candidate source or final state differs')
        cs = memory['ownership_storage']['components']
        fields = dict(baseline['graph_fields'])
        audit_path = directory / 'checked.json'
        audited = False
        if audit_path.exists():
            audit = read(audit_path)
            audited = (audit['program_sha256'] == program['sha256']
                       and audit['every_run_graph_and_ordered_audits_equal'] is True
                       and audit['run_checks'] == checked['run_checks']
                       and audit['final_state'] == checked['final_state'])
            if not audited:
                raise ValueError('candidate Run audit differs')
        candidates[str(budget)] = dict(
            program_sha256=raw['sha256'], memory_sha256=digest(directory / 'memory.json'),
            graph_bytes=memory['graph_owned_teardown_bytes'],
            graph_saved=baseline['graph_owned_teardown_bytes'] - memory['graph_owned_teardown_bytes'],
            program_bytes=memory['retained_program_teardown_bytes'],
            process_peak=memory['execution_and_takeover_peak_bytes'],
            components=len(cs), frame_widths=dict(collections.Counter(len(c['frames']) for c in cs)),
            signal_slots=sum(len(c['signals']) for c in cs), final_state_exact=True,
            physical_owners=memory['source_storage']['completed_owners']['owners'],
            completed_owner_records_bytes=memory['source_storage']['completed_owner_records_bytes'],
            run_graph_and_ordered_audits_checked=audited,
            graph_field_deltas={k: v-fields[k] for k, v in memory['graph_fields'] if v != fields[k]})
    return dict(scope='actual standalone Cell runtime; memory and observed work, not timing',
        program_sha256=program['sha256'], trace_sha256=digest(root / 'trace.json'),
        checked_sha256=digest(root / 'checked.json'), runs=observed['runs'],
        baseline_graph=baseline['graph_owned_teardown_bytes'],
        baseline_program=baseline['retained_program_teardown_bytes'],
        baseline_physical_owners=baseline['source_storage']['completed_owners']['owners'],
        baseline_completed_owner_records_bytes=baseline['source_storage']['completed_owner_records_bytes'],
        proposal_count=len(trace['records']),
        repeated_shared_proposals=sum(r['matched_births'] > 1 and r['available_shared_inputs'] > 0 for r in trace['records']),
        cursor_history=dict(events=len(depths), depth_histogram=dict(collections.Counter(depths)),
            cross_run_edges=cross_run, uncompiled_roots=history['uncompiled_root_events']),
        pre_apply_rhs_outcomes=dict(saturation), multi_source_applications_by_width=dict(widths),
        candidates=candidates,
        limitations=['Proposal alternatives overlap; observed applies are not committed mutations or saved work.',
            'Cursor ancestry and ownership-component composition are distinct; root-only history is not proof of no cross-stage data reuse.',
            'Final-state equality does not replace per-Run checks for candidates marked unchecked.',
            'Resident Program and process peak remain charged; Graph savings alone do not establish total-memory improvement.',
            'Historical 30% target and saturated-stage RHS skipping remain unfinished.'])


if __name__ == '__main__':
    root, baseline, program, output = map(pathlib.Path, sys.argv[1:])
    output.write_text(json.dumps(summarize(root, baseline, program), indent=2) + '\n')
