#!/usr/bin/env python3
"""Fifth-change checkpoint for worker constructor-prefix continuation."""
import argparse
import json
import os
from pathlib import Path
import runpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('current', 'prior', 'tag', 'historical', 'sum_program', 'ray_program', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    harness = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'witness-prefix/measure.py'))
    for group in ('cell_execution', 'query_workers'):
        harness['GROUPS'][group] = (group,)
    os.environ.pop('CELL_CPU_PROGRESS', None)
    os.environ.pop('CELL_CPU_PROFILE', None)
    common = ['--repair-ports', '--entry-publications', '--cell-absorption']
    parallel = ['--query-workers', '4', '--parallel-residuals', '--parallel-publication']
    continuation = ['--cell-execution-grain', '1']
    for case, program, repeats in [('sum', args.sum_program, 5), ('ray', args.ray_program, 3)]:
        lanes = {name: {'runtime': str(binary.resolve()), 'program': str(program.resolve()), 'args': common + flags}
                 for name, binary, flags in [
                     ('prior4_g1', args.prior, parallel + continuation),
                     ('tag4', args.tag, parallel), ('historical4', args.historical, parallel),
                     ('current_serial', args.current, []), ('current4', args.current, parallel),
                     ('prefix4_g1', args.current, parallel + continuation),
                 ]}
        manifest = {'scope': 'standalone Cell CPU; worker constructor-prefix checkpoint', 'lanes': lanes}
        (args.output / (case + '-manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
        harness['measure'](manifest, args.output / case, repeats, 1, 90)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main()
