#!/usr/bin/env python3
"""Collect completed checkpoints across resumed learning segments.

SPEC: {case: {reference: ITERATE_DIR, segments: [ITERATE_DIR, ...]}}.
Only the final segment must contain a completed program; every included round
must preserve the original graph, schedule and ordered RHS stamp.
"""
import argparse
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def collect(spec):
    results = {}
    keys = ('final_state_sha256', 'schedule_sha256', 'ordered_rhs_sha256')
    for case, config in spec.items():
        reference = read(Path(config['reference']) / 'rounds.json')[-1]
        expected = [reference[k] for k in keys]
        segments = []
        for folder in config['segments']:
            rounds = read(Path(folder) / 'rounds.json')
            assert rounds
            for r in rounds:
                assert [r[k] for k in keys] == expected, (case, folder, r['round'])
            segments.append({'rounds': rounds})
        final = Path(config['segments'][-1])
        program = read(final / 'program.json')
        entries = read(final / 'expanded.json')
        results[case] = dict(reference_units=reference['units'], program_sha256=program['sha256'],
            limits=program['iterative_bake']['limits'],
            all_completed_checkpoints_match_reference=True,
            no_counter_pruning=all(r['work']['counter_prunes'] == 0 for s in segments for r in s['rounds']),
            segments=segments)
        # An actually applied unit illustrates the certificate. Visits are not
        # per-unit receipt hits and do not count committed mutations.
        applied = segments[-1]['rounds'][-1]['work']['applied_units']
        candidates = [e for e in entries if e['terminal'].get('queries') and applied.get(str(e['id']), 0)]
        if candidates:
            example = max(candidates, key=lambda e: applied[str(e['id'])])
            rule = example['expanded'][-1][1][0]
            rules = program['recipe']['rules']
            results[case]['example'] = dict(unit=example, applied_visits=applied[str(example['id'])],
                consumer=rules[rule], donors={str(q['rule']): rules[q['rule']] for q in example['terminal']['queries']})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(read(args.spec)), indent=2) + '\n')
