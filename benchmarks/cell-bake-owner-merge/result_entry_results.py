"""Compare installed RHS-result catalogs with the same-runtime seed control."""
import json
import pathlib
import sys

CASES = ('fact', 'loopfact', 'sum-bits', 'dot-product')
WORK = ('signal_bindings_created', 'signal_bindings_live', 'composition_entry_reads',
        'composition_result_writes', 'composition_result_joins',
        'composition_transition_probes', 'composition_substituted_ports',
        'composition_shape_builds', 'boundary_edges_created', 'owned_live')
MEMORY = ('graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
          'execution_and_takeover_peak_bytes', 'max_takeover_extra_bytes')


def read(path):
    return json.loads(path.read_text())


def compare(root):
    lanes = ('rhs-result-control', 'rhs-result-learning')
    checks = [{r['case']: r for r in read(root / lane / 'checked.json')['cases']}
              for lane in lanes]
    learned = {r['case']: r for r in read(root / lanes[1] / 'learning.json')['cases']}
    rows = []
    for name in CASES:
        checked = [c[name] for c in checks]
        memory = [read(root / lane / name / 'full-memory.json') for lane in lanes]
        for c, m in zip(checked, memory):
            if not c['all_saved_run_checks_equal'] or c['program'] != m['program_sha256']:
                raise ValueError(f'{name}: unaudited or mismatched memory program')
            if c['final_state'] != m['final_state_sha256'] or c['runs'] != m['runs']:
                raise ValueError(f'{name}: memory execution differs from audited execution')
        if checked[0]['final_state'] != checked[1]['final_state'] or checked[0]['runs'] != checked[1]['runs']:
            raise ValueError(f'{name}: control/candidate execution differs')
        if learned[name]['seed_program'] != checked[0]['program']:
            raise ValueError(f'{name}: incorrect learning control')
        stats = [c['ownership']['stats'] for c in checked]
        row = {'case': name, 'runs': checked[0]['runs'],
               'control_program': checked[0]['program'], 'candidate_program': checked[1]['program'],
               'saved_run_checks_equal': True, 'memory_final_states_equal': True,
               'added_result_fragments': learned[name]['added_result_fragments'],
               'work': {k: [s[k] for s in stats] for k in WORK},
               'source_storage': {k: [c['source_storage'][k] for c in checked] for k in
                                  ('completed_owner_frames', 'explicit_cell_slots', 'completed_owner_records_bytes',
                                   'fact_record_live_bytes', 'cell_slot_bytes', 'writer_bytes')},
               'key_lookup_calls': [c['key_lookup_calls'] for c in checked],
               'memory': {k: [m[k] for m in memory] for k in MEMORY},
               'graph_field_deltas': {k: dict(memory[1]['graph_fields']).get(k, 0) - v
                                      for k, v in memory[0]['graph_fields']}}
        row['graph_reduction_percent'] = 100 * (1 - memory[1][MEMORY[0]] / memory[0][MEMORY[0]])
        rows.append(row)
    return {'scope': 'standalone Cell CPU runtime; same-runtime seed versus learned result catalog; no timing or native semantic claim',
            'pair_order': ['control', 'candidate'], 'cases': rows}


if __name__ == '__main__':
    result = compare(pathlib.Path(sys.argv[1]))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
