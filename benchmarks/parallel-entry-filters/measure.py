#!/usr/bin/env python3
"""Frozen normal-binary Raytrace comparison; retain every interleaved sample."""
import json
from pathlib import Path
import runpy
import sys


def main(binary, program, output):
    harness = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'witness-prefix/measure.py'))
    harness['GROUPS']['sieve'] = ('sieve',)
    harness['GROUPS']['query_workers'] = ('query_workers',)
    common = ['--repair-ports', '--entry-publications', '--cell-absorption']
    lanes = {}
    for label, count, enabled in [('serial', 0, False), ('point4', 4, False),
                                  ('filter4', 4, True), ('filter8', 8, True)]:
        flags = common.copy()
        if count:
            flags += ['--query-workers', str(count), '--query-grain', '64']
        if enabled:
            flags += ['--parallel-entry-filters']
        lanes[label] = {'runtime': str(binary), 'program': str(program), 'args': flags}
    # The runtime treats presence of CELL_CPU_PROFILE as enabled: remove it.
    import os
    os.environ.pop('CELL_CPU_PROFILE', None)
    os.environ.pop('CELL_CPU_PROGRESS', None)
    manifest = {'scope': 'standalone Cell CPU, not native egglog; complete Raytrace; normal binary', 'lanes': lanes}
    output.parent.mkdir(parents=True, exist_ok=True)
    (output.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    harness['measure'](manifest, output, 3, 1, 90)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main(*(Path(p).resolve() for p in sys.argv[1:]))
