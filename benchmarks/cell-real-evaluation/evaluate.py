#!/usr/bin/env python3
"""Independent finite-domain evaluator for dense latent Cell models.

Adapters expose encode(facts), step(latent, action_ids), decode(latent).
Only encode sees symbolic observations, once at each initial state. Decode is
for scoring; its result NEVER feeds the latent recurrence. Neither an adapter
nor this evaluator may use a teacher/nearest-state lookup in step().
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def module(path, name):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def scores(adapter, latent, truth):
    output = np.asarray(adapter.decode(latent))
    if output.shape != truth.shape:
        raise ValueError('decoder shape mismatch')
    finite = np.isfinite(output).all(axis=1) & np.isfinite(latent).all(axis=1)
    wrong = (output >= .5) != (truth >= .5)
    wrong[~finite] = True
    return dict(rows=len(truth), exact_rows=int((~wrong.any(axis=1)).sum()),
                wrong_bits=int(wrong.sum()), nonfinite_rows=int((~finite).sum()))


def merge_counts(items):
    return {key: sum(x[key] for x in items) for key in ('rows', 'exact_rows', 'wrong_bits', 'nonfinite_rows')}


def same_observations(adapter, left, right):
    a, b = np.asarray(adapter.decode(left)), np.asarray(adapter.decode(right))
    finite = np.isfinite(a).all(axis=1) & np.isfinite(b).all(axis=1)
    return int((finite & ((a >= .5) == (b >= .5)).all(axis=1)).sum())


def evaluate(adapter, batch_size=512):
    teacher = module(ROOT / 'benchmarks/cell-real-state/study.py', 'latent_evaluation_teacher')
    states, facts, targets, train, valid, test = teacher.dataset()
    test_ids = np.flatnonzero(test)
    initial = np.asarray(adapter.encode(facts[test_ids]))
    initial_check = scores(adapter, initial, facts[test_ids])
    pairs = np.array([(i, a, b) for i in test_ids for a in range(17) for b in range(17)])
    two_step, reverse_step, commute = [], [], 0
    repeat_first, repeat_second, repeat_equal = [], [], 0
    destination_train, destination_held, boundary_feedback = [], [], []
    # Exhaust all ordered pairs from each held-out initial structural state.
    for start in range(0, len(pairs), batch_size):
        ids, a, b = pairs[start:start+batch_size].T
        z = np.asarray(adapter.encode(facts[ids]))
        za = np.asarray(adapter.step(z.copy(), a))
        zab = np.asarray(adapter.step(za.copy(), b))
        zb = np.asarray(adapter.step(z.copy(), b))
        zba = np.asarray(adapter.step(zb.copy(), a))
        dest = targets[targets[ids, a], b]
        two_step.append(scores(adapter, zab, facts[dest]))
        reverse_step.append(scores(adapter, zba, facts[dest]))
        commute += same_observations(adapter, zab, zba)
    edges = np.array([(i, a) for i in test_ids for a in range(17)])
    for start in range(0, len(edges), batch_size):
        ids, a = edges[start:start+batch_size].T
        z = np.asarray(adapter.encode(facts[ids]))
        once = np.asarray(adapter.step(z, a))
        twice = np.asarray(adapter.step(once.copy(), a))
        truth = facts[targets[ids, a]]
        repeat_first.append(scores(adapter, once, truth))
        dest = targets[ids, a]
        in_train = train[dest]
        for mask, collected in ((in_train, destination_train), (~in_train, destination_held)):
            if mask.any():
                collected.append(scores(adapter, once[mask], truth[mask]))
        # Rule-enable events that newly merge boundary ports (rather than only
        # constructor results) isolate actual feedback in this finite teacher.
        boundary_columns = [teacher.PAIRS.index(pair) for pair in teacher.BASE_PAIRS]
        feedback = (a >= 15) & (facts[ids][:, boundary_columns] != truth[:, boundary_columns]).any(axis=1)
        if feedback.any():
            boundary_feedback.append(scores(adapter, once[feedback], truth[feedback]))
        repeat_second.append(scores(adapter, twice, truth))
        repeat_equal += same_observations(adapter, once, twice)
    sequences = []
    for seed, length in [(20261112, 12), (104729, 12), (65537, 48)]:
        rng = np.random.default_rng(seed)
        ids = np.tile(test_ids, 4)
        actions = rng.integers(0, 17, size=(length, len(ids)))
        actions[2] = 15; actions[5] = 16; actions[8] = actions[7]
        current = np.asarray(adapter.encode(facts[ids]))
        all_exact = np.ones(len(ids), dtype=bool)
        checkpoints = []
        teacher_forced_exact = np.ones(len(ids), dtype=bool)
        for action in actions:
            # Diagnostic upper comparison: fresh teacher input for each step.
            # This separate state never modifies the autonomous recurrence.
            forced = adapter.step(np.asarray(adapter.encode(facts[ids])), action)
            current = np.asarray(adapter.step(current, action))
            ids = targets[ids, action]
            out = np.asarray(adapter.decode(current))
            finite = np.isfinite(out).all(axis=1) & np.isfinite(current).all(axis=1)
            exact = finite & ((out >= .5) == (facts[ids] >= .5)).all(axis=1)
            all_exact &= exact
            forced_out = np.asarray(adapter.decode(forced))
            teacher_forced_exact &= (np.isfinite(forced_out).all(axis=1)
                                     & np.isfinite(forced).all(axis=1)
                                     & ((forced_out >= .5) == (facts[ids] >= .5)).all(axis=1))
            checkpoints.append(dict(exact_rows=int(exact.sum()), nonfinite_rows=int((~finite).sum())))
        sequences.append(dict(seed=seed, steps=length, trajectories=len(ids),
                              all_steps_exact=int(all_exact.sum()),
                              teacher_forced_all_steps_exact=int(teacher_forced_exact.sum()), checkpoints=checkpoints))
    forward, reverse = merge_counts(two_step), merge_counts(reverse_step)
    one, twice = merge_counts(repeat_first), merge_counts(repeat_second)
    passed = all(c['rows'] == c['exact_rows'] for c in (initial_check, forward, reverse, one, twice))
    passed &= all(s['all_steps_exact'] == s['trajectories'] for s in sequences)
    return dict(evaluation_status='complete', finite_checks_pass=bool(passed),
                native_semantic_acceptance=False, runtime_takeover=False,
                held_initial_states=len(test_ids), initial_reconstruction=initial_check,
                one_step=one, two_step=forward, reverse_two_step=reverse,
                one_step_target_train=merge_counts(destination_train),
                one_step_target_held=merge_counts(destination_held),
                rule_enabled_boundary_feedback=merge_counts(boundary_feedback),
                repeated_event=twice, idempotent_observation_pairs=repeat_equal,
                commuting_observation_pairs=commute, ordered_event_pairs=len(pairs), sequences=sequences,
                teacher_sha256=hashlib.sha256((ROOT/'benchmarks/cell-real-state/study.py').read_bytes()).hexdigest(),
                corpus_sha256=hashlib.sha256(repr(states).encode()+targets.tobytes()).hexdigest())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--adapter', type=Path, required=True)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--precision', default=None)
    args = p.parse_args()
    impl = module(args.adapter.resolve(), 'latent_external_adapter')
    adapter = (impl.load_adapter(args.weights.resolve(), precision=args.precision)
               if args.precision else impl.load_adapter(args.weights.resolve()))
    with np.errstate(over='ignore', invalid='ignore'):
        result = evaluate(adapter)
    result['adapter_sha256'] = hashlib.sha256(args.adapter.read_bytes()).hexdigest()
    result['evaluator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['weights_sha256'] = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    result['implementation_sha256'] = {
        name: hashlib.sha256((ROOT / 'benchmarks' / name / 'study.py').read_bytes()).hexdigest()
        for name in ('cell-real-state', 'cell-real-algebra', 'cell-real-joint')
    }
    result['precision_option'] = args.precision
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='sequences'}, indent=2))


if __name__ == '__main__':
    main()
