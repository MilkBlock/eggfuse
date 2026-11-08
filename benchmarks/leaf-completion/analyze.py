#!/usr/bin/env python3
"""Collect typed admission and audited replay results; never infer speed from units.

SPEC is {case: {program, profile, variants: {label: iterate_output_dir}}}.
Every variant must have completed iterate successfully. Its semantic stamp is
compared with every other variant/round in that case, in the compiler domain.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def collect(spec):
    result = {}
    stamp_keys = ('final_state_sha256', 'schedule_sha256', 'ordered_rhs_sha256')
    for case, paths in spec.items():
        program, profile = read(paths['program']), read(paths['profile'])
        assert profile['program_sha256'] == program['sha256']
        visits = collections.Counter()
        for prefix in profile['prefixes']:
            _, _, c, pivot = prefix['edge']
            visits[c, pivot] += prefix['visits']
        stages = {(e['rule'], e['anchor']): e['atoms']
                  for e in program['multi_stage']['stage_entries']}
        entries, shape_counts, shape_visits = [], collections.Counter(), collections.Counter()
        for (r, pivot), n in sorted(visits.items()):
            order = stages[r, pivot]
            query = program['recipe']['rules'][r]['query']
            primitive = any('primitive' in query[a]['call'] for a in order)
            shape = 'primitive_steps' if primitive else 'multiple_table_ports' if len(order) > 1 else 'legacy_shape'
            shape_counts[shape] += 1
            shape_visits[shape] += n
            entries.append(dict(rule=r, pivot=pivot, visits=n, steps=len(order), shape=shape))
        row = dict(program_sha256=program['sha256'], profile_file_sha256=sha(paths['profile']),
                   observed_entries=len(visits), resumptions=sum(visits.values()),
                   shape_counts=dict(shape_counts), shape_visits=dict(shape_visits),
                   entries=entries, variants={})
        reference = None
        for label, folder in paths['variants'].items():
            folder = Path(folder)
            rounds, p = read(folder / 'rounds.json'), read(folder / 'program.json')
            for round in rounds:
                stamp = [round[k] for k in stamp_keys]
                if reference is None:
                    reference = stamp
                assert stamp == reference, (case, label, round['round'], stamp, reference)
            leaves = p['spine_blocks']['entries']
            admitted = {(e['consumer'], e['pivot']) for e in leaves}
            row['variants'][label] = dict(program_sha256=p['sha256'],
                leaf_count=len(leaves), staged_leaves=sum(bool(e['block'].get('steps')) for e in leaves),
                observed_entries_covered=len(admitted & visits.keys()),
                observed_visits_covered=sum(visits[e] for e in admitted),
                rounds=rounds)
        row['compiler_stamps_agree'] = True
        result[case] = row
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(read(args.spec)), indent=2) + '\n')
