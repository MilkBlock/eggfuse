"""Repeat the three exact GPU schedules, balancing order within every graph."""
import argparse
from itertools import permutations
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from evaluate import dataset, device, endpoint_ok, prepare_plan, run
from fit import digest


@torch.inference_mode()
def measure(root):
    baseline = root / 'results.json'
    first = json.loads(baseline.read_text())['timings']['heldout']
    modes = ('barrier_min', 'local', 'barrier')
    indices = first['local']['indices']
    for mode in modes:
        assert first[mode]['indices'] == indices
    data = dataset('heldout')
    plan, dev = prepare_plan(), device()
    traces = {}
    for mode in modes:
        with np.load(root / 'traces' / f'heldout--{mode}.npz', allow_pickle=False) as archive:
            traces[mode] = dict(archive)
    elapsed = {mode: [] for mode in modes}
    for mode in modes:
        for index in indices[:4]:
            run(data, slice(index, index + 1), mode, None, False, plan, dev)
            torch.mps.synchronize()
    orders = list(permutations(modes))
    for repeat in range(len(orders)):
        rows = {mode: [] for mode in modes}
        saved = []
        for j, index in enumerate(indices):
            sample = slice(index, index + 1)
            for mode in orders[(repeat + j) % len(orders)]:
                start = perf_counter_ns()
                state, _, _ = run(data, sample, mode, None, False, plan, dev)
                torch.mps.synchronize()
                rows[mode].append((perf_counter_ns() - start) / 1e6)
                saved.append((state, mode, sample))
        for state, mode, sample in saved:
            endpoint_ok(state, traces[mode], sample)
        for mode in modes:
            elapsed[mode].append(rows[mode])
    medians = {m: [median(times) for times in values] for m, values in elapsed.items()}
    differences = np.asarray(elapsed['local']) - np.asarray(elapsed['barrier_min'])
    return dict(reference_sha256=digest(baseline), indices=indices, samples_ms=elapsed,
                round_medians_ms=medians,
                paired_difference_per_round_ms=np.median(differences, axis=1).tolist(),
                paired_difference_ms=float(np.median(differences)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    report = measure(args.root)
    (args.root / 'repeat-timing.json').write_text(json.dumps(report) + '\n')
    print(report['round_medians_ms'], report['paired_difference_per_round_ms'])
