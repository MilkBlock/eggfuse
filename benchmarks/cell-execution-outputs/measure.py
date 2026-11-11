#!/usr/bin/env python3
"""Five-change checkpoint including the immediate output-ownership control."""
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
    harness['GROUPS']['cell_execution'] = ('cell_execution',)
    harness['GROUPS']['query_workers'] = ('query_workers',)
    harness['GROUPS']['owned_output_storage'] = ('stage_spine', 'owned_output_storage')
    os.environ.pop('CELL_CPU_PROGRESS', None)
    os.environ.pop('CELL_CPU_PROFILE', None)
    common = ['--repair-ports', '--entry-publications', '--cell-absorption']
    parallel = ['--query-workers', '4', '--parallel-residuals', '--parallel-publication']
    for case, program, repeats in [('sum', args.sum_program, 5), ('ray', args.ray_program, 3)]:
        lanes = {name: {'runtime': str(binary.resolve()), 'program': str(program.resolve()), 'args': common + flags}
                 for name, binary, flags in [
                     ('prior4', args.prior, parallel), ('tag4', args.tag, parallel),
                     ('historical4', args.historical, parallel), ('current_serial', args.current, []),
                     ('current4', args.current, parallel),
                     ('resumed4_g1', args.current, parallel + ['--cell-execution-grain', '1']),
                 ]}
        manifest = {'scope': 'standalone Cell CPU; independent result ownership checkpoint', 'lanes': lanes}
        (args.output / (case + '-manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
        harness['measure'](manifest, args.output / case, repeats, 1, 90)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main()
