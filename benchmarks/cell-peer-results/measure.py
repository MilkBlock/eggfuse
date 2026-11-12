#!/usr/bin/env python3
"""Five-commit checkpoint: peer slots, ready-queue control and archived runtime."""
import argparse
import json
from pathlib import Path
import runpy
import statistics


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('current', 'prior', 'historical', 'sum_program', 'ray_program', 'output', 'summary'):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    a.output.mkdir()
    base = Path(__file__).resolve().parents[1]
    harness = runpy.run_path(str(base / 'witness-prefix/measure.py'))
    harness['GROUPS']['cell_execution'] = ('cell_execution',)
    harness['GROUPS']['query_workers'] = ('query_workers',)
    common = ['--repair-ports', '--entry-publications', '--cell-absorption']
    parallel = ['--query-workers', '4', '--parallel-residuals', '--parallel-publication']
    summary = {'scope': 'standalone Cell CPU, not native egglog',
               'limits': 'Small interleaved fresh-process sample. Counts are work, not utilization. All samples retained.',
               'workloads': {}}
    for case, program, repeat in [('sum', a.sum_program, 5), ('ray', a.ray_program, 3)]:
        lanes = {name: {'runtime': str(binary.resolve()), 'program': str(program.resolve()), 'args': common + flags}
                 for name, binary, flags in [
                     ('control4', a.prior, parallel + ['--cell-execution-grain', '1']),
                     ('peer4', a.current, parallel + ['--cell-execution-grain', '1']),
                     ('peer_serial', a.current, ['--query-workers', '1', '--cell-execution-grain', '1']),
                     ('historical4', a.historical, parallel)]}
        spec = {'scope': summary['scope'], 'lanes': lanes}
        (a.output / f'{case}-manifest.json').write_text(json.dumps(spec, indent=2) + '\n')
        harness['measure'](spec, a.output / case, repeat, 1, 120)
        raw = json.loads((a.output / case / 'samples.json').read_text())
        frozen = json.loads((base / 'cell-ready-scheduler/results.json').read_text())
        assert raw['semantic_reference']['state_sha256'] == frozen['workloads'][case]['state_sha256']
        result = {'repeat': repeat, 'warmups': 1, 'execution_order': raw['execution_order'],
                  'semantics': raw['semantic_reference'], 'lanes': {}}
        for name, lane in raw['lanes'].items():
            fields = ('iteration', 'inference_seconds', 'process_wall_seconds', 'process_user_seconds', 'process_system_seconds')
            result['lanes'][name] = {k: lane[k] for k in ('runtime_sha256', 'program_file_sha256', 'args')}
            result['lanes'][name].update({
                'warmups': [{k: row[k] for k in fields} for row in lane['warmup_samples']],
                'samples': [{k: row[k] for k in fields} for row in lane['samples']],
                'inference_median': statistics.median(row['inference_seconds'] for row in lane['samples']),
                'wall_median': statistics.median(row['process_wall_seconds'] for row in lane['samples'])})
        values = result['lanes']
        result['peer_over_control'] = values['peer4']['inference_median'] / values['control4']['inference_median']
        result['peer_over_serial'] = values['peer4']['inference_median'] / values['peer_serial']['inference_median']
        result['peer_over_historical'] = values['peer4']['inference_median'] / values['historical4']['inference_median']
        summary['workloads'][case] = result
        a.summary.write_text(json.dumps(summary, indent=2) + '\n')
        print(case, {name: v['inference_median'] for name, v in values.items()}, flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main()
