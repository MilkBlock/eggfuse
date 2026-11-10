#!/usr/bin/env python3
"""Bounded semantic/work checks; no timing campaign or native execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text())

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate', type=Path)
    p.add_argument('baseline', type=Path)
    p.add_argument('sum_program', type=Path)
    p.add_argument('fixture_program', type=Path)
    p.add_argument('saved_semantic', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    a.output.mkdir()
    cases = [('sum', a.sum_program, False, 64), ('fixture', a.fixture_program, True, 64),
             ('fixture-collisions', a.fixture_program, True, 0)]
    result = {'scope': 'standalone Cell CPU; one process per semantic/work configuration; not a speed measurement',
              'baseline_commit': 'efc06d49', 'binaries': {'baseline':sha(a.baseline), 'candidate':sha(a.candidate)},
              'cases': {}}
    keys = ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')
    for case, program, audit, bits in cases:
        reference = None
        evidence = {}
        for lane, workers in [('baseline', None), ('off', None), ('inline', 1), ('two', 2), ('four', 4)]:
            binary = a.baseline if lane == 'baseline' else a.candidate
            directory = a.output / f'{case}-{lane}'
            argv = [str(binary.resolve()), '--program', str(program.resolve()), '--output', str(directory.resolve()), '--local-congruence']
            if audit: argv.append('--audit-stages')
            if workers is not None: argv += ['--query-workers', str(workers), '--query-grain', '1' if case == 'sum' else '16']
            start = time.monotonic()
            with (a.output / f'{case}-{lane}.log').open('w') as log:
                subprocess.run(argv, env=dict(os.environ, CELL_CPU_HASH_BITS=str(bits)), stdout=log,
                               stderr=subprocess.STDOUT, timeout=10, check=True)
            elapsed = time.monotonic() - start
            report = read(directory / 'report.json')
            assert report['status'] == 'complete'
            runs = [[s[k] for k in keys] for s in report['steps']]
            files = ['state.json'] + (['stages.json', 'binding-audit.json'] if audit else [])
            stamp = {f: sha(directory/f) for f in files}
            stamp['runs'] = hashlib.sha256(json.dumps(runs).encode()).hexdigest()
            if reference is None: reference = stamp
            assert stamp == reference, (case, lane, stamp, reference)
            evidence[lane] = {'diagnostic_process_seconds':elapsed, 'argv':argv, 'hash_bits':bits,
                'runs':len(runs), 'hashes':stamp, 'report_sha256':sha(directory/'report.json'),
                'query_workers':report.get('query_workers'), 'key_lookup_calls':report['key_lookup_calls'],
                'stats':report['stats'], 'stage_spine':report['stage_spine']['stats'], 'neighbor_context':report['neighbor_context']}
            if workers is not None:
                assert report['query_workers']['stats']['spine_entries'] > 0
                assert report['query_workers']['stats']['answers'] > 0
                assert report['query_workers']['stats']['entries'] == sum(report['query_workers']['stats']['worker_entries'])
        result['cases'][case] = {'program_sha256':sha(program), 'lanes':evidence}
    semantic = a.output / 'semantic'
    semantic.mkdir()
    for name in ['native-source.json','native-legacy.json','native-values.json','sum-legacy']:
        (semantic/name).symlink_to((a.saved_semantic/name).resolve())
    (semantic/'run-legacy').symlink_to((a.output/'sum-baseline').resolve())
    (semantic/'run-values').symlink_to((a.output/'sum-four').resolve())
    checker = Path(__file__).parents[1] / 'marker-handoff/choice_diagnosis.py'
    subprocess.run(['python3', str(checker), str(semantic), str(a.output/'semantic-acceptance.json')], check=True)
    acceptance = read(a.output/'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    result['semantic_acceptance'] = acceptance
    (a.output/'checks.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({case:{lane: row['query_workers'] for lane,row in data['lanes'].items()}
                      for case,data in result['cases'].items()}, indent=2))

if __name__ == '__main__': main()
