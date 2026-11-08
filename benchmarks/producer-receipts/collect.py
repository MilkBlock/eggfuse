#!/usr/bin/env python3
"""Collect completed learning variants, rejecting divergent semantic stamps.

SPEC: {case: {reference: ITERATE_DIR, variants: {label: ITERATE_DIR}}}.
Interrupted diagnostics are kept separately and are never a learned variant.
"""
import argparse
import json
from pathlib import Path


def collect(spec):
    result = {}
    keys = ('final_state_sha256', 'schedule_sha256', 'ordered_rhs_sha256')
    for case, paths in spec.items():
        reference = json.loads((Path(paths['reference']) / 'rounds.json').read_text())
        expected = [reference[0][k] for k in keys]
        variants = {}
        for label, folder in {'staged_reference': paths['reference'], **paths['variants']}.items():
            folder = Path(folder)
            program = json.loads((folder / 'program.json').read_text())
            rounds = json.loads((folder / 'rounds.json').read_text())
            for r in rounds:
                assert [r[k] for k in keys] == expected, (case, label, r['round'])
            variants[label] = dict(program_sha256=program['sha256'],
                matching_leaves=len(program['spine_blocks']['entries']),
                producer_roots=program['iterative_bake'].get('producer_roots', []),
                limits=program['iterative_bake']['limits'],
                no_counter_pruning=all(r['work']['counter_prunes'] == 0 for r in rounds),
                rounds=rounds)
        result[case] = dict(all_completed_rounds_match_reference=True, variants=variants)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(json.loads(args.spec.read_text())), indent=2) + '\n')
