"""Paired frozen-model replay timings; observed CPU routes, not native execution."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import dataset
from packed_cell_replay import prepare, executor, costs, audit


def timed(call):
    start = time.monotonic(); value = call()
    return value, time.monotonic()-start


def main():
    p = argparse.ArgumentParser()
    p.add_argument('trace', type=Path)
    p.add_argument('baseline', type=Path); p.add_argument('candidate', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args(); raw = read_bytes(a.trace); trace = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if not mx.metal.is_available():
        raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    runs = {}; results = {}; reference = None
    for label, path in [('baseline', a.baseline), ('candidate', a.candidate)]:
        report = json.loads(path.with_suffix('.json').read_text())
        if report['provenance']['test_trace'] != digest:
            raise ValueError('trace mismatch')
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['model_sha256']:
            raise ValueError('model mismatch')
        with np.load(path) as model:
            nodes, encoding_seconds = timed(lambda: dataset(trace, int(model['channels']), bool(model['zero_role_channels']), str(model['encoding'])))
            # Equal population and output targets, despite different context routes.
            target = np.array([n['target'] for n in nodes])
            if reference is not None and not np.array_equal(reference, target):
                raise ValueError('target population changed')
            reference = target
            plan, plan_seconds = timed(lambda: prepare(nodes, 'two'))
            run, setup_seconds = timed(lambda: executor(nodes, model['w'], model['coef'], plan, True))
            cold, cold_seconds = timed(run)
            cold = np.array(cold)
            cpu_run, cpu_setup = timed(lambda: executor(nodes, model['w'], model['coef'], plan, False))
            cpu, cpu_seconds = timed(cpu_run)
        runs[label] = run
        results[label] = dict(model_sha256=report['model_sha256'], costs=costs(plan),
            encoding_seconds=encoding_seconds, plan_seconds=plan_seconds,
            gpu_setup_seconds=setup_seconds, gpu_cold_seconds=cold_seconds,
            cpu_setup_seconds=cpu_setup, cpu_execute_seconds=cpu_seconds,
            numeric_audit=audit(cold, cpu), warm_gpu_seconds=[])
    for iteration in range(6):
        for label in (['baseline', 'candidate'] if iteration % 2 == 0 else ['candidate', 'baseline']):
            _, elapsed = timed(runs[label]); results[label]['warm_gpu_seconds'].append(elapsed)
    for result in results.values():
        result['warm_gpu_median_seconds'] = float(np.median(result['warm_gpu_seconds']))
    output = dict(scope='Standalone frozen-model numeric replay with observed CPU wiring; no matching, lifecycle, or semantic completion',
        trace_sha256=digest, runs=results,
        median_replay_ratio=results['baseline']['warm_gpu_median_seconds']/results['candidate']['warm_gpu_median_seconds'],
        limitations=['Cold timing includes execution compilation; paired warm timing reuses plans',
                     'Preparation, upload/setup and CPU numeric audit reported separately',
                     'CPU timing is NumPy execution of the numeric model, not egglog or Eggfuse',
                     'Final-state transfer and semantic Eq readout/audit are not included in warm GPU timing',
                     'Models have different accuracy; runtime ratio alone cannot authorize replacement'])
    a.output.write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(output, indent=2))
    if not all(r['numeric_audit']['passed'] for r in results.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
