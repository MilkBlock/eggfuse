#!/usr/bin/env python3
"""Run emitted Cell history chains with frozen runtimes; no timing campaign."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from check_links import sha


def run(root, cases=('chain', 'retired'), audit=True):
    records = []
    suffix = '' if audit else '-normal'
    for case in cases:
        fixture = root / f'fixture-{case}'
        program = fixture / 'program.json'
        for bits in (64, 0):
            for lane in ('baseline', 'candidate'):
                runtime = root / f'runtime-{lane}'
                argv = [str(runtime), '--program', str(program), '--output', str(fixture / f'{lane}-{bits}{suffix}'),
                        '--local-congruence']
                if audit:
                    argv.append('--audit-stages')
                env = {'CELL_CPU_HASH_BITS': str(bits)}
                start = time.monotonic()
                with (fixture / f'{lane}-{bits}{suffix}.log').open('w') as log:
                    subprocess.run(argv, env=dict(os.environ, **env), stdout=log, stderr=subprocess.STDOUT,
                                   timeout=5, check=True)
                elapsed = time.monotonic() - start
                records.append(dict(case=case, lane=lane, bits=bits, argv=argv, env=env,
                    runtime_sha256=sha(runtime), program_sha256=sha(program), diagnostic_process_seconds=elapsed))
                (root / f'fixture-runs{suffix}.json').write_text(json.dumps(records, indent=2) + '\n')
                assert elapsed < 1, (case, lane, bits, elapsed)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    run(p.parse_args().root)
