#!/usr/bin/env python3
"""Short work/semantic checks on the actual completion path; no timing campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['compiler', 'baseline', 'candidate', 'sum_program', 'ray_program', 'saved_semantic', 'output']:
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    results = {'scope': 'standalone Cell CPU; full short sum-bits and a 128-Run Raytrace prefix; not speed measurements',
               'binaries': {name: sha(getattr(args, name)) for name in ['compiler', 'baseline', 'candidate']},
               'cases': {}}
    run_fields = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed']
    for case, program, limit in [('sum', args.sum_program, 10000), ('ray128', args.ray_program, 128)]:
        baked = args.output / (case + '-baked')
        command = [str(args.compiler.resolve()), 'bake-cell-completion', '--program', str(program.resolve()), '--output', str(baked.resolve())]
        with (args.output / (case + '-compile.log')).open('w') as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        compiled = read(baked / 'program.json')
        assert compiled['recipe'] == read(program)['recipe']
        reference = None
        lanes = {}
        for lane, binary, artifact, workers in [
            ('baseline', args.baseline, program, 0),
            ('off', args.candidate, baked / 'program.json', 0),
            ('four', args.candidate, baked / 'program.json', 4),
        ]:
            output = args.output / f'{case}-{lane}'
            command = [str(binary.resolve()), str(artifact.resolve()), str(output.resolve()), str(limit), str(workers), '64']
            with (args.output / f'{case}-{lane}.log').open('w') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=10)
            report = read(output / 'report.json')
            runs = [[s[k] for k in run_fields] for s in report['steps']]
            raw_state = sha(output / 'state.json')
            state_value = read(output / 'state.json')
            state = hashlib.sha256(json.dumps(state_value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if reference is None:
                reference = (state_value, runs)
            assert (state_value, runs) == reference, (case, lane)
            spine = report['stage_spine']['stats']
            lanes[lane] = {
                'state_sha256': state, 'runs': len(runs),
                'state_file_sha256': raw_state,
                'runs_sha256': hashlib.sha256(json.dumps(runs).encode()).hexdigest(),
                'key_lookup_calls': report['key_lookup_calls'],
                'stats': {k: report['stats'].get(k) for k in ['handoff_attempts', 'handoff_closed', 'rhs_frames_avoided', 'register_result_writes', 'union_requests']},
                'spine': {k: v for k, v in spine.items() if k.startswith('ripsat_') or k in [
                    'history_capture_reads', 'history_slots_written', 'history_allocations', 'history_inherited_reads',
                    'history_shared_slots', 'effect_slots_initialized', 'effect_slot_probes', 'effect_output_copies',
                    'output_registrations', 'cell_output_slot_reads', 'cell_output_deliveries', 'joint_history_frames']},
            }
        switch = compiled['iterative_bake']['rhs_handoffs']
        contracts = compiled['iterative_bake']['completion']['contracts']
        results['cases'][case] = {'source_program_sha256': sha(program), 'candidate_program_sha256': sha(baked / 'program.json'),
                                  'direct_states': sum(s is not None for s in switch['completion_states']),
                                  'structures': len(contracts['structures']), 'implementations': len(contracts['implementations']),
                                  'inferred_entries': len(compiled['iterative_bake'].get('completion_extensions', [])),
                                  'native_transitions': compiled['iterative_bake']['completion']['cell_egraph']['completion_transitions'], 'lanes': lanes}
        if case == 'sum':
            assert lanes['four']['spine']['ripsat_completed'] > 0, 'semantic parity alone does not establish takeover coverage'
    semantic = args.output / 'semantic'
    semantic.mkdir()
    for name in ['native-source.json', 'native-legacy.json', 'native-values.json', 'sum-legacy']:
        (semantic / name).symlink_to((args.saved_semantic / name).resolve())
    (semantic / 'run-legacy').symlink_to((args.output / 'sum-baseline').resolve())
    (semantic / 'run-values').symlink_to((args.output / 'sum-four').resolve())
    checker = Path(__file__).parents[1] / 'marker-handoff/choice_diagnosis.py'
    acceptance = args.output / 'semantic-acceptance.json'
    subprocess.run(['python3', str(checker), str(semantic), str(acceptance)], check=True)
    results['semantic_acceptance'] = read(acceptance)
    assert results['semantic_acceptance']['status'] == 'pass'
    (args.output / 'checks.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps({name: {'direct_states': row['direct_states'], 'completed': row['lanes']['four']['spine']['ripsat_completed']}
                      for name, row in results['cases'].items()}))


if __name__ == '__main__':
    main()
