#!/usr/bin/env python3
"""Run short mixed-boundary Cell checks against frozen runtimes; no timing."""
import argparse
from pathlib import Path
import subprocess
from run_view_fixtures import run
from run_retention_fixtures import run as run_direct


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--direct-emitter', type=Path)
    args = p.parse_args()
    source = Path('tools/cell-compiler/tests/fixtures/mixed-cell-outputs.egg').read_text()
    aliased = source.replace('(Out E))', '(Out E) (Missing E))').replace(
        '(rule ((Start x y)) ((Gateway x) (F x)) :ruleset make)',
        '(rule ((Start x y) (= f (F x))) ((F x) (Gateway x) (F x)) :ruleset make)\n'
        '(rule ((Start x y)) ((Gateway x) (delete (Missing x)) (F y)) :ruleset make)')
    bodies = {'mixed': source, 'aliased': aliased}
    if args.direct_emitter:
        for case, text in bodies.items():
            source = args.root / f'{case}.egg'
            source.write_text(text)
            with (args.root / f'emit-{case}.log').open('w') as log:
                subprocess.run([str(args.direct_emitter), str(source), str(args.root / f'fixture-{case}')],
                    stdout=log, stderr=subprocess.STDOUT, check=True)
        run_direct(args.root, bodies)
    else:
        run(args.root, args.root / 'compiler', bodies)
