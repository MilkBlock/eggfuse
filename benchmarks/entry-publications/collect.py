#!/usr/bin/env python3
"""Collect completed node-publication audits and bounded marginal-work trials.

ROOT is the experiment output directory documented in README.md. Large graph
exports are hashed by the existing audit/measurement runners, then removed.
"""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def collect(root, prefix=''):
    result = {'scope': 'standalone Cell CPU; observed-operation credit, not latency credit',
              'compiler_sha256': sha(root / (prefix + 'compiler')), 'cases': {}}
    for case, directory in [('sum-bits', 'learn-sum'), ('raytrace', 'learn-raytrace')]:
        folder = root / (prefix + directory)
        rounds = read(folder / 'rounds.json')
        program = read(folder / 'program.json')
        assert program['sha256'] == rounds[-1]['source_program']
        stamps = ('final_state_sha256', 'schedule_sha256', 'ordered_rhs_sha256',
                  'ordered_writes_sha256', 'ordered_resumes_sha256')
        for r in rounds:
            assert all(r[k] == rounds[0][k] for k in stamps)
            credit = r['credit']
            assert credit['policy'] == 'measured-work'
            for trial in credit.get('trials', []):
                assert trial['semantic_audit'] is True
                counters = trial['work']['counters']
                assert all(v['before'] - v['after'] == v['saved'] for v in counters.values())
                assert sum(v['saved'] for v in counters.values()) == trial['work']['net_saved_operations']
            if r['admitted']:
                assert len(r['admitted']) == 1
                assert credit['selected_net_saved_operations'] > 0
        result['cases'][case] = {'program_file_sha256': sha(folder / 'program.json'), 'rounds': rounds}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prefix', default='')
    args = parser.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.prefix), indent=2) + '\n')
