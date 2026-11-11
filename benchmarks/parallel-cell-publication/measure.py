#!/usr/bin/env python3
"""Five-implementation checkpoint: freeze inputs and interleave all samples."""
import argparse
import json
import os
from pathlib import Path
import runpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('current', 'before_merge', 'last_checkpoint', 'sum_program', 'ray_program', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    harness = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'witness-prefix/measure.py'))
    for name in ('query_workers', 'publication', 'sieve'):
        harness['GROUPS'][name] = (name,)
    os.environ.pop('CELL_CPU_PROFILE', None)
    os.environ.pop('CELL_CPU_PROGRESS', None)
    common = ['--repair-ports', '--entry-publications', '--cell-absorption']
    for workload, program, repeats in [('sum', args.sum_program, 7), ('ray', args.ray_program, 5)]:
        lanes = {}
        for label, runtime, workers, enabled in [
            ('checkpoint_serial', args.last_checkpoint, 0, False),
            ('current_serial', args.current, 0, False),
            ('before4', args.before_merge, 4, True),
            ('current1', args.current, 1, True),
            ('current4', args.current, 4, True),
            ('current8', args.current, 8, True),
        ]:
            flags = common.copy()
            if workers:
                flags += ['--query-workers', str(workers), '--query-grain', '64']
            if enabled:
                flags += ['--parallel-residuals', '--parallel-publication']
            lanes[label] = {'runtime':str(runtime.resolve()), 'program':str(program.resolve()), 'args':flags}
        spec = {'scope':'standalone Cell CPU, not native egglog; complete workloads', 'lanes':lanes}
        (args.output / (workload + '-manifest.json')).write_text(json.dumps(spec, indent=2) + '\n')
        harness['measure'](spec, args.output / workload, repeats, 1, 90)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main()
