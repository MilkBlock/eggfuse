"""Summarize saved observations and candidate heaps without new executions."""
import collections
import json
import sys
from pathlib import Path
from pool import canonical


def read(path):
    return json.loads(path.read_text())


def summarize(root):
    names = [c['case'] for c in read(root/'manifest.json')['cases']]
    observations = []
    for name in names:
        o = read(root/name/'catalog-observation.json')
        seed = read(root/name/'candidate.json')
        assert o['source_program'] == seed['sha256']
        prefixes = {canonical(dict(f, hops=f['hops'][:n])) for f in seed['ownership_fragments']['fragments']
                    for n in range(1, len(f['hops'])+1)}
        covered = 0
        lengths = collections.Counter()
        for r in o['catalog_trace']['records']:
            last = r['fragment']['hops'][-1]
            shape = o['ownership_storage']['shapes'][r['source_shape']]
            pair = {'root': shape['programs'][last['source_frame']], 'hops': [dict(last, source_frame=0)]}
            covered += canonical(pair) in prefixes
            lengths[len(r['fragment']['hops'])] += 1
        outcomes = collections.Counter()
        for row in o['catalog_trace']['saturation']['rows']:
            outcomes[row['outcome']] += row['counts']['applications']
        observations.append(dict(case=name, source_program=o['source_program'], runs=o['runs'],
                                 all_run_checks_equal=o['all_saved_run_checks_equal'],
                                 uncovered_births=o['catalog_trace']['uncovered_births'],
                                 proposal_paths=len(o['catalog_trace']['records']),
                                 already_installed_local_pair=covered, proposal_hops=dict(lengths),
                                 saturation_applications_by_outcome=dict(outcomes)))
    pooled = read(root/'passive'/'summary.json')
    variants = []
    for variant in pooled['variants']:
        directory = root/'passive'/f"budget{variant['budget']}"
        compiled = {r['case']: r for r in read(directory/'compiled.json')['cases']}
        checked_path = directory/'checked.json'
        checked = {r['case']: r for r in read(checked_path)['cases']} if checked_path.exists() else {}
        cases = []
        for name in names:
            before = read(root/name/'candidate-live-parent-owner-heap.json')
            after = read(directory/name/'heap.json')
            assert before['final_state_sha256'] == after['final_state_sha256']
            assert after['program_sha256'] == compiled[name]['program']
            admitted = name in checked and checked[name]['program'] == after['program_sha256'] and checked[name]['all_saved_run_checks_equal']
            old_fields = dict(before['graph_fields'])
            cases.append(dict(case=name, program=after['program_sha256'],
                              graph_before=before['graph_owned_teardown_bytes'], graph_after=after['graph_owned_teardown_bytes'],
                              source_records_before=before['source_storage']['completed_owners']['source_records'],
                              source_records_after=after['source_storage']['completed_owners']['source_records'],
                              explicit_slots_before=before['source_storage']['explicit_cell_slots'],
                              explicit_slots_after=after['source_storage']['explicit_cell_slots'],
                              program_delta=after['retained_program_teardown_bytes']-before['retained_program_teardown_bytes'],
                              changed_graph_fields={k: v-old_fields.get(k, 0) for k, v in after['graph_fields'] if v != old_fields.get(k, 0)},
                              all_seed_transitions_preserved=compiled[name]['all_seed_transitions_preserved'],
                              final_state_equal=True, all_run_checks_equal=bool(admitted)))
        variants.append(dict(budget=variant['budget'], added_paths=variant['added_paths'],
                             maximal_paths=variant['maximal_paths'], cases=cases,
                             all_inputs_reduce_graph=all(c['graph_after'] < c['graph_before'] for c in cases)))
    return dict(scope='actual standalone Cell runtime; one audited batch, two offline selections; no speed or native-generalization claim',
                observations=observations, pooled_records=pooled['records'], portable_proposals=pooled['portable_proposals'],
                variants=variants, admission='neither variant replaces the shared seed: loopfact Graph regresses',
                limits=['The 64-path candidate has final-state checks only; the 256-path candidate has full saved Run and terminal-effect checks.',
                        'Saturation outcomes are aggregated across age buckets. Raw age flags from the pre-fix capture undercount transferred frames.',
                        'Logical facts and source identities remain; more physical takeovers do not establish large egraph compression.'])


if __name__ == '__main__':
    root, output = map(Path, sys.argv[1:])
    output.write_text(json.dumps(summarize(root), indent=2)+'\n')
