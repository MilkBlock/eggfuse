#!/usr/bin/env python3
"""Compare one short standalone Cell CPU execution per lane; not a timing test.

Build runtime alone with sparse-cells,view-ports,storage-metrics,
slot-transfer-audit,spine-shapes,allocation-metrics. Retain full reports locally;
commit compact counters and exact state/ordered-trace digests, never binaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def counters(value):
    if isinstance(value, dict):
        return {k: counters(v) for k, v in value.items() if not k.endswith('_seconds')}
    if isinstance(value, list):
        return [counters(v) for v in value]
    return value


def compare(baseline, candidate, program, output):
    output.mkdir(parents=True, exist_ok=False)
    result = {
        'scope': 'standalone Cell CPU; short counter and ordered semantic audit; not timing or native egglog',
        'program': str(program), 'program_sha256': sha(program),
        'args': ['--local-congruence'], 'lanes': {},
    }
    sources = sorted(Path('engine/cell-runtime/src').rglob('*.rs'))
    sources += [Path('engine/cell-runtime/Cargo.toml'), Path('Cargo.lock')]
    result['candidate_source_manifest'] = {str(p): sha(p) for p in sources}
    result['comparison_script_sha256'] = sha(__file__)
    reference = None
    for name, runtime in [('baseline', baseline), ('candidate', candidate)]:
        directory = output / name
        command = [str(runtime), '--program', str(program), '--output', str(directory), *result['args']]
        with (output / f'{name}.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        report = json.loads((directory / 'report.json').read_text())
        assert report['status'] == 'complete'
        hashes = {file: sha(directory / file) for file in ['state.json', 'rhs.json', 'writes.json', 'resumes.json']}
        schedule = [[step[k] for k in KEYS] for step in report['steps']]
        shape = json.loads((directory / 'spine-shapes.json').read_text())
        shape.pop('program_sha256', None)
        hashes.update(schedule=digest(schedule), spine_shape=digest(shape))
        if reference is None:
            reference = hashes
        assert hashes == reference, (name, hashes, reference)
        selected = {k: counters(report[k]) for k in ['stats', 'allocations', 'setup_allocations',
            'key_lookup_calls', 'fact_decode_calls', 'fact_decode_ports', 'known_results']}
        selected.update(stage_spine=counters(report['stage_spine']['stats']),
                        maintenance=counters(report['maintenance']['stats']),
                        witness_plan=report['multi_stage'].get('witness_plan'))
        result['lanes'][name] = {'runtime': str(runtime), 'runtime_sha256': sha(runtime),
            'runs': len(schedule), 'hashes': hashes, 'counters': selected}
    # A missing old counter is explicitly absent from the delta, never zero.
    old, new = [result['lanes'][name]['counters'] for name in ('baseline', 'candidate')]
    deltas = {}
    def diff(a, b, path=''):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a.keys() & b.keys():
                diff(a[k], b[k], path + '/' + k)
        elif type(a) is int and type(b) is int:
            deltas[path] = b - a
    diff(old, new)
    result['common_counter_deltas'] = dict(sorted(deltas.items()))
    (output / 'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('Verified', len(schedule), 'ordered Runs; key lookups', old['key_lookup_calls'], '->', new['key_lookup_calls'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'candidate', 'program', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    compare(args.baseline, args.candidate, args.program, args.output)
