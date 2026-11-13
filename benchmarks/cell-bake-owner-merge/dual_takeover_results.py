"""Full-memory paired audit of actual installed dual-source takeover."""
import json
import pathlib
import sys

MEMORY = ('graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
          'execution_and_takeover_peak_bytes', 'max_takeover_extra_bytes')
WORK = ('dual_candidates', 'dual_admissions', 'dual_pending_skips', 'dual_symbol_checks',
        'dual_source_moves', 'dual_field_moves', 'dual_temporary_bytes', 'dual_bindings_retired',
        'components_live', 'signal_bindings_live', 'owned_live', 'boundary_live',
        'boundary_edges_created', 'boundary_edges_removed', 'boundary_probes',
        'signal_root_queries', 'signal_parent_probes', 'composition_unbaked_fallbacks')


def read(path):
    return json.loads(path.read_text())


def summarize(root, candidate_variant="dual-source-takeover", memory_file="dual-memory.json"):
    candidate = {c['case']: c for c in read(root / candidate_variant / 'checked.json')['cases']}
    control = {c['case']: c for c in read(root / 'prefix-all/checked.json')['cases']}
    rows = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        memories = [read(root / variant / name / memory_file)
                    for variant in ('prefix-all', candidate_variant)]
        for check, memory in zip((control[name], candidate[name]), memories):
            if check['all_saved_run_checks_equal'] is not True or check['program'] != memory['program_sha256']:
                raise ValueError('unaudited memory identity')
            if check['runs'] != memory['runs'] or check['final_state'] != memory['final_state_sha256']:
                raise ValueError('memory execution differs from audited final state')
        if memories[0]['final_state_sha256'] != memories[1]['final_state_sha256']:
            raise ValueError('different final state')
        stats = [m['ownership_query_work'] for m in memories]
        if stats[0]['dual_admissions'] != 0:
            raise ValueError('control already uses takeover')
        rows.append({'case': name, 'runs': candidate[name]['runs'],
                     'programs': [m['program_sha256'] for m in memories],
                     'saved_run_checks_equal': True, 'final_states_equal': True,
                     'memory': {k: [m[k] for m in memories] for k in MEMORY},
                     'work': {k: [s[k] for s in stats] for k in WORK},
                     'route_probes': [s.get('dual_route_probes') for s in stats],
                     'plan_summary': candidate[name]['ownership']['plan_summary'],
                     'source_storage': {k: [m['source_storage'][k] for m in memories] for k in
                                        ('completed_owner_frames', 'explicit_cell_slots', 'cell_slot_bytes',
                                         'fact_record_live_bytes', 'completed_owner_records_bytes')},
                     'graph_field_deltas': {k: dict(memories[1]['graph_fields']).get(k, 0) - v
                                            for k, v in memories[0]['graph_fields']},
                     'graph_reduction_percent': 100 * (1 - memories[1][MEMORY[0]] / memories[0][MEMORY[0]])})
    return {'scope': 'same frozen binary, standalone Cell CPU Graph and retained Program heap; no native acceptance or speed claim',
            'pair_order': ['seed control', 'dual-source takeover'], 'cases': rows}


if __name__ == '__main__':
    pathlib.Path(sys.argv[2]).write_text(json.dumps(summarize(pathlib.Path(sys.argv[1]), *sys.argv[3:]), indent=2) + '\n')
