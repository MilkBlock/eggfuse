#!/usr/bin/env python3
"""Run the emitted short Entry fixtures against frozen diagnostic binaries.

This checks work and ordered state, not performance. Emit fixtures first with
the cell compiler's emit_cell_entry_fixtures example. Output directories must
not exist; use a fresh experiment root for another comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def run(root):
    records = []
    for case in ('reused', 'replaced'):
        for lane in ('baseline', 'candidate'):
            binary = root / f'runtime-{lane}-audit'
            program = root / 'fixtures' / f'{case}.json'
            output = root / 'fixtures' / f'{case}-{lane}'
            if output.exists():
                raise SystemExit(f'refusing to overwrite {output}')
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            args = [str(binary), '--program', str(program), '--output', str(output),
                    '--local-congruence', '--audit-stages']
            start = time.monotonic()
            process = subprocess.run(args, capture_output=True, text=True, timeout=5, check=True)
            elapsed = time.monotonic() - start
            output.with_suffix('.log').write_text(process.stdout + process.stderr)
            records.append({'case': case, 'lane': lane, 'argv': args,
                            'runtime_sha256': digest, 'diagnostic_process_seconds': elapsed})
            (root / 'fixtures/runs.json').write_text(json.dumps(records, indent=2) + '\n')
            if elapsed >= 1:
                raise SystemExit(f'{case}/{lane} exceeded the short-fixture budget: {elapsed:.3f}s')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    run(parser.parse_args().root)
