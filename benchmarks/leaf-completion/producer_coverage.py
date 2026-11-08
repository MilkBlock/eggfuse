#!/usr/bin/env python3
"""Compare observed producers with leaf coverage and static typed eligibility.

The synthetic profile only queries compiler eligibility for all certified stage
entries. It is never installed as a learned catalog or counted as execution.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def coverage(program_path, profile_path, leaves_path, baker):
    program = json.loads(program_path.read_text())
    profile = json.loads(profile_path.read_text())
    leaves = json.loads(leaves_path.read_text())
    assert profile['program_sha256'] == program['sha256']
    assert leaves['recipe']['sha256'] == program['recipe']['sha256']
    sources = collections.Counter()
    for prefix in profile['prefixes']:
        sources[prefix['edge'][0]] += prefix['visits']
    selected = {e['consumer'] for e in leaves['spine_blocks']['entries']}
    stages = program['multi_stage']['stage_entries']
    query = dict(schema='eggfuse-spine-shapes/v1', program_sha256=program['sha256'],
                 prefixes=[dict(edge=[0, 0, e['rule'], e['anchor']], visits=1) for e in stages])
    with tempfile.TemporaryDirectory(prefix='cell-static-eligibility-') as tmp:
        tmp = Path(tmp)
        (tmp / 'query.json').write_text(json.dumps(query))
        result = tmp / 'eligible.json'
        subprocess.run([str(baker), str(program_path), str(tmp / 'query.json'),
                        str(program_path), str(result), str(len(stages)), '--complete-stage'], check=True)
        raw = result.read_bytes()
        eligible = collections.defaultdict(list)
        for e in json.loads(raw)['spine_blocks']['entries']:
            eligible[e['consumer']].append(e['pivot'])
    return dict(scope='observed outgoing winning transitions; visits are not distinct producer executions',
                profile_sha256=hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                static_eligibility_artifact_sha256=hashlib.sha256(raw).hexdigest(),
                observed_producer_rules=len(sources),
                missing_from_staged_leaves=[dict(rule=r, outgoing_visits=n, statically_eligible_pivots=eligible.get(r, []))
                                            for r, n in sorted(sources.items()) if r not in selected])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('program', 'profile', 'leaves', 'baker', 'output'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(coverage(args.program, args.profile, args.leaves, args.baker), indent=2) + '\n')
