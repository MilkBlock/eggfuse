#!/usr/bin/env python3
"""Exercise shared Cell pair predicates against frozen runtimes; no speed claim."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from check_links import sha


def run(root, compiler, bodies=None):
    source = Path('tools/cell-compiler/tests/fixtures/view-consumers.egg').read_text()
    bodies = bodies or {
        'dispatch': source,
        'overlap': source.replace('(< cost bound)', '(<= cost bound)'),
        'reversed': source.replace('(< cost bound)', '(> bound cost)').replace('(> cost bound)', '(< bound cost)'),
        'guards': source.replace('(< cost bound)', '(< cost bound) (<= cost bound)'),
    }
    records = []
    for case, body in bodies.items():
        fixture = root / f'fixture-{case}'
        fixture.mkdir()
        source_path = fixture / 'source.egg'
        source_path.write_text(body)
        with (fixture / 'compile.log').open('w') as log:
            subprocess.run([str(compiler), 'compile', '--source', str(source_path),
                '--output', str(fixture / 'compiled')], stdout=log, stderr=subprocess.STDOUT, check=True)
        program = fixture / 'compiled/program.json'
        for bits in (64, 0):
            for lane in ('baseline', 'candidate'):
                runtime = root / f'runtime-{lane}'
                args = [str(runtime), '--program', str(program), '--output', str(fixture / f'{lane}-{bits}'),
                        '--local-congruence', '--audit-stages']
                env = dict(os.environ, CELL_CPU_HASH_BITS=str(bits))
                start = time.monotonic()
                with (fixture / f'{lane}-{bits}.log').open('w') as log:
                    subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, timeout=5, check=True, env=env)
                elapsed = time.monotonic() - start
                records.append(dict(case=case, lane=lane, bits=bits, argv=args, env={'CELL_CPU_HASH_BITS':str(bits)},
                    runtime_sha256=sha(runtime), program_sha256=sha(program), diagnostic_process_seconds=elapsed))
                (root / 'fixture-runs.json').write_text(json.dumps(records, indent=2) + '\n')
                assert elapsed < 1, f'{case}/{lane}/{bits} exceeded short-fixture budget: {elapsed}'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--compiler', type=Path, default=Path('target/cell-unification-tests/debug/eggfuse-cell-compiler'))
    args = p.parse_args()
    run(args.root, args.compiler)
