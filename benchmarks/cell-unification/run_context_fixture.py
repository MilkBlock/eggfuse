#!/usr/bin/env python3
"""Run one small guarded-prefix differential check with two frozen runtimes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(root, compiler):
    source = Path(__file__).resolve().with_name('context-branches.egg')
    fixture = root / 'fixture'
    fixture.mkdir(exist_ok=True)
    with (fixture / 'compile.log').open('w') as log:
        subprocess.run([str(compiler), 'compile', '--source', str(source), '--output',
                        str(fixture / 'compiled')], stdout=log, stderr=subprocess.STDOUT, check=True)
    raw = json.loads((fixture / 'compiled/program.json').read_text())
    # Explicit test admission of a compiler-certified context, not learned
    # performance evidence. The parser re-derives and validates all cuts.
    ids = [i for i, r in enumerate(raw['recipe']['rules'])
           if r['metadata']['name'] in ('guarded-prefix', 'linear-prefix')]
    assert len(ids) == 2 and all(raw['context_cuts'][rid] for rid in ids)
    raw['context_admission'] = {'schema': 'eggfuse-context-admission/v1',
        'recipe': raw['recipe']['sha256'], 'rules': ids}
    raw.pop('sha256', None)
    raw['sha256'] = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'),
                                             ensure_ascii=True).encode()).hexdigest()
    program = fixture / 'program.json'
    program.write_text(json.dumps(raw, indent=2) + '\n')
    for lane in ('baseline', 'candidate'):
        with (fixture / f'{lane}.log').open('w') as log:
            subprocess.run([str(root / f'runtime-{lane}'), '--program', str(program),
                '--output', str(fixture / lane), '--audit-stages', '--local-congruence'],
                stdout=log, stderr=subprocess.STDOUT, check=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--compiler', type=Path,
                   default=Path('target/cell-unification-tests/debug/eggfuse-cell-compiler'))
    args = p.parse_args()
    run(args.root, args.compiler)
