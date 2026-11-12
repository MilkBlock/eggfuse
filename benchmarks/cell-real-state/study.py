#!/usr/bin/env python3
"""Dense real latent-state research; NOT the production Cell runtime.

A fixed finite constructor graph supplies an exact symbolic teacher. The
learned transition never sees its decoded facts during autonomous rollout.
PCA, ridge decoders and transition models use disjoint structural state splits.
"""
import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path

import numpy as np

PAIRS = list(itertools.combinations(range(18), 2))
BASE_PAIRS = list(itertools.combinations(range(6), 2))
# Result nodes 6..17. Shared subterms, two-argument constructors and reconvergence.
NODES = [("F", (0,)), ("F", (1,)), ("F", (2,)),
         ("G", (2, 3)), ("G", (0, 4)), ("G", (1, 5)),
         ("H", (6, 9)), ("H", (7, 10)), ("H", (8, 11)),
         ("Pair", (0, 3)), ("Pair", (1, 4)), ("Pair", (2, 5))]


def require(ok, why):
    if not ok:
        raise ValueError(why)


def partitions(n):
    if not n:
        yield ()
        return
    for p in partitions(n - 1):
        for i in range(max(p, default=-1) + 2):
            yield p + (i,)


def close(partition, flags, action=None):
    parent = list(range(18))

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a == b:
            return False
        parent[max(a, b)] = min(a, b)
        return True

    first = {}
    for i, key in enumerate(partition):
        union(i, first.setdefault(key, i))
    if action is not None:
        if action < len(BASE_PAIRS):
            union(*BASE_PAIRS[action])
        else:
            flags |= 1 << (action - len(BASE_PAIRS))
    while True:
        changed = False
        keys = {}
        for node, (op, args) in enumerate(NODES, 6):
            key = (op, tuple(find(i) for i in args))
            if key in keys:
                changed = union(node, keys[key]) or changed
            else:
                keys[key] = node
        if flags & 1:
            for a, b, out1, out2 in [(0, 3, 6, 9), (1, 4, 7, 10), (2, 5, 8, 11)]:
                if find(a) == find(b):
                    changed = union(out1, out2) or changed
        if flags & 2:
            if find(12) == find(13) and find(2) == find(4):
                changed = union(0, 5) or changed
            if find(6) == find(11) and find(1) == find(3):
                changed = union(2, 4) or changed
        if not changed:
            break
    return tuple(find(i) for i in range(18)), flags


def dataset():
    states = sorted({close(p, flags) for p in partitions(6) for flags in range(4)})
    lookup = {s: i for i, s in enumerate(states)}
    facts = np.array([[int(p[i] == p[j]) for i, j in PAIRS] + [f & 1, (f >> 1) & 1]
                      for p, f in states], dtype=np.float32)
    targets = np.array([[lookup[close(p, f, a)] for a in range(17)] for p, f in states])
    split = np.array([int.from_bytes(hashlib.sha256(repr(s).encode()).digest()[:4], 'little') % 10
                      for s in states])
    # No held-out structural state can be a training source OR training target.
    train, valid, test = split < 6, (split >= 6) & (split < 8), split >= 8
    require(train.sum() and valid.sum() and test.sum(), "empty split")
    return states, facts, targets, train, valid, test


def validate_teacher(states, targets):
    """Independent bitset closure with all constructor pairs, no union-find."""
    def reference(partition, flags, action):
        rows = [sum(1 << j for j, key in enumerate(partition) if key == partition[i])
                for i in range(18)]

        def add(a, b):
            rows[a] |= 1 << b; rows[b] |= 1 << a

        if action < 15:
            add(*BASE_PAIRS[action])
        else:
            flags |= 1 << (action-15)
        while True:
            before = rows.copy()
            for k in range(18):
                for i in range(18):
                    if rows[i] >> k & 1:
                        rows[i] |= rows[k]
            for i, (op1, args1) in enumerate(NODES, 6):
                for j, (op2, args2) in enumerate(NODES, 6):
                    if op1 == op2 and all(rows[a] >> b & 1 for a, b in zip(args1, args2)):
                        add(i, j)
            if flags & 1:
                for a, b, i, j in [(0, 3, 6, 9), (1, 4, 7, 10), (2, 5, 8, 11)]:
                    if rows[a] >> b & 1:
                        add(i, j)
            if flags & 2:
                if rows[12] >> 13 & 1 and rows[2] >> 4 & 1:
                    add(0, 5)
                if rows[6] >> 11 & 1 and rows[1] >> 3 & 1:
                    add(2, 4)
            if rows == before:
                return tuple((row & -row).bit_length()-1 for row in rows), flags

    for i, (p, f) in enumerate(states):
        for a in range(17):
            require(reference(p, f, a) == states[targets[i, a]], 'teacher implementations disagree')
    for a in range(17):
        require(np.array_equal(targets[targets[:, a], a], targets[:, a]), 'non-idempotent teacher action')
        for b in range(17):
            require(np.array_equal(targets[targets[:, a], b], targets[targets[:, b], a]), 'noncommuting positive closure actions')
    return dict(status='pass', checked_transitions=len(states)*17,
                idempotent_actions=17, commuting_action_pairs=17*17,
                scope='finite model only; no native egglog acceptance')


def ridge(x, y, regularization=1.0):
    x, y = x.astype(np.float64), y.astype(np.float64)
    mx, my = x.mean(0), y.mean(0)
    xc, yc = x - mx, y - my
    if x.shape[1] <= len(x):
        w = np.linalg.solve(xc.T @ xc + regularization * np.eye(x.shape[1]), xc.T @ yc)
    else:
        w = xc.T @ np.linalg.solve(xc @ xc.T + regularization * np.eye(len(x)), yc)
    # Model execution uses FP16 coefficients and FP32 accumulations like the
    # prior ridge study, but omits its storage-only scale-256 convention.
    b = my - mx @ w
    require(np.isfinite(w.astype(np.float16)).all(), "FP16 weight overflow")
    return w.astype(np.float16).astype(np.float32), b.astype(np.float32)


def predict(x, model):
    w, b = model
    return x.astype(np.float16).astype(np.float32) @ w + b


def error(scores, truth, varying):
    wrong = (scores >= .5) != (truth >= .5)
    return dict(exact_state_rate=float((~wrong.any(axis=1)).mean()),
                wrong_bits=int(wrong.sum()), rows=len(truth),
                variable_bit_error=float(wrong[:, varying].mean()),
                false_positive=int((wrong & (scores >= .5)).sum()),
                false_negative=int((wrong & (scores < .5)).sum()))


class Transition:
    def __init__(self, kind, dimension, hidden, rng):
        self.kind = kind
        self.dimension = dimension
        self.hidden = hidden
        # Event vectors are dense signed real values, not target-dependent labels.
        self.events = rng.normal(size=(17, 16)).astype(np.float32)
        self.events /= np.linalg.norm(self.events, axis=1, keepdims=True)
        if kind == 'nonlinear':
            self.a = rng.normal(size=(dimension + 16, hidden)).astype(np.float32)
            self.a *= np.sqrt(2 / (dimension + 16))
            self.bias = rng.uniform(-1, 1, hidden).astype(np.float32)
        elif kind == 'bilinear':
            self.gate = rng.normal(size=(16, 8)).astype(np.float32)

    def features(self, z, actions):
        if self.kind.startswith('switched'):
            if self.kind == 'switched-linear':
                return z
            i, j = np.triu_indices(self.dimension)
            return np.concatenate([z, z[:, i] * z[:, j]], axis=1)
        e = self.events[actions]
        base = np.concatenate([z, e], axis=1)
        if self.kind == 'linear':
            return base
        if self.kind == 'bilinear':
            return np.concatenate([base, (z[:, :, None] * (e @ self.gate)[:, None, :]).reshape(len(z), -1)], axis=1)
        # Dense mixing and smooth nonlinearity; no decoded bit vector, symbolic
        # guard, nearest-state lookup or oracle projection occurs here.
        mixed = base.astype(np.float16).astype(np.float32) @ self.a.astype(np.float16).astype(np.float32)
        return np.concatenate([base, np.tanh(mixed + self.bias)], axis=1)

    def fit(self, z, actions, target):
        if self.kind.startswith('switched'):
            features = self.features(z, actions)
            self.bank = [ridge(features[actions == a], (target - z)[actions == a]) for a in range(17)]
            return
        self.model = ridge(self.features(z, actions), target - z)

    def step(self, z, actions):
        if self.kind.startswith('switched'):
            features = self.features(z, actions)
            result = z.copy()
            for a, model in enumerate(self.bank):
                selected = actions == a
                result[selected] += predict(features[selected], model)
            return result.astype(np.float16).astype(np.float32)
        return (z + predict(self.features(z, actions), self.model)).astype(np.float16).astype(np.float32)

    def parameter_count(self):
        return sum(x.size for x in self.__dict__.values() if isinstance(x, np.ndarray)) + (
            sum(x.size for model in self.bank for x in model) if hasattr(self, 'bank') else sum(x.size for x in self.model))


def invariant_span(facts, targets, cutoff=1e-8):
    """Finite-domain rank diagnostic, uses ALL states, not a held-out model.

    Smallest joint invariant function space containing the linear readouts.
    Ranks are floating SVD diagnostics at a stated tolerance, not exact proofs.
    """
    def basis(x):
        u, s, _ = np.linalg.svd(x.astype(np.float64), full_matrices=False)
        return u[:, s > max(s[0] * cutoff, 1e-12)]

    z = basis(np.column_stack([np.ones(len(facts)), facts]))
    dimensions = [z.shape[1]]
    for _ in range(len(facts)):
        # Incremental projection avoids a very wide (states x actions*rank) SVD.
        previous = z.shape[1]
        old = z
        for a in range(17):
            shifted = old[targets[:, a]]
            residual = shifted - z @ (z.T @ shifted)
            residual -= z @ (z.T @ residual)
            u, s, _ = np.linalg.svd(residual, full_matrices=False)
            extra = u[:, s > cutoff]
            if extra.shape[1]:
                z = np.column_stack([z, extra])
        dimensions.append(z.shape[1])
        if z.shape[1] == previous:
            break
    residual = max(float(np.max(np.abs(z[targets[:, a]] - z @ (z.T @ z[targets[:, a]])))) for a in range(17))
    return dict(dimensions=dimensions, final_dimension=z.shape[1],
                maximum_invariance_residual=residual, singular_cutoff=cutoff,
                scope='all finite states, linear state/action operators and linear readouts only; not a nonlinear lower bound')


def evaluate_transition(model, z, facts, targets, source, decoder, varying):
    ids = np.repeat(np.flatnonzero(source), 17)
    actions = np.tile(np.arange(17), source.sum())
    dest = targets[ids, actions]
    predicted = model.step(z[ids], actions)
    score = error(predict(predicted, decoder), facts[dest], varying)
    score['latent_rmse'] = float(np.sqrt(np.mean((predicted - z[dest]) ** 2)))
    changed = dest != ids
    score['changed'] = error(predict(predicted[changed], decoder), facts[dest[changed]], varying)
    score['no_op'] = error(predict(predicted[~changed], decoder), facts[dest[~changed]], varying)
    return score


def rollout(model, z, facts, targets, source, decoder, varying, seed=91):
    rng = np.random.default_rng(seed)
    ids = np.tile(np.flatnonzero(source), 4)
    # Runs with repeated/no-op events, rule activation and new equivalences.
    actions = rng.integers(0, 17, size=(12, len(ids)))
    actions[2] = 15; actions[5] = 16; actions[8] = actions[7]
    current = z[ids].copy()
    trace_ok = np.ones(len(ids), dtype=bool)
    steps = []
    for event in actions:
        with np.errstate(over='ignore', invalid='ignore'):
            current = model.step(current, event)
        if not np.isfinite(current).all():
            return dict(steps=steps, all_steps_exact_rate=0.0, trajectories=len(ids),
                        nonfinite_at_step=len(steps)+1), actions
        ids = targets[ids, event]
        scores = predict(current, decoder)
        exact = ((scores >= .5) == (facts[ids] >= .5)).all(axis=1)
        trace_ok &= exact
        steps.append(error(scores, facts[ids], varying))
    return dict(steps=steps, all_steps_exact_rate=float(trace_ok.mean()),
                latent_max_abs=float(np.abs(current).max()), trajectories=len(ids)), actions


def train_nonlinear(z, facts, targets, train, valid, decoder, varying):
    """Train hidden weights and readout through three autonomous steps.

    Teacher states appear only as loss targets, never as intermediate inputs.
    This is an additional model family, not the unchanged ridge baseline.
    """
    rng = np.random.default_rng(991)
    d, hidden = z.shape[1], 128
    model = Transition('nonlinear', d, hidden, rng)
    sources, action = np.where(train[:, None] & train[targets])
    model.fit(z[sources], action, z[targets[sources, action]])
    start_ids = rng.choice(np.flatnonzero(train), 4096)
    ids = start_ids.copy()
    events, truth_ids = [], []
    allowed = [np.flatnonzero(train[targets[i]]) for i in range(len(z))]
    for _ in range(3):
        event = np.array([rng.choice(allowed[i]) for i in ids])
        ids = targets[ids, event]
        events.append(event); truth_ids.append(ids)
    params = [model.a.copy(), model.bias.copy(), model.model[0].copy(), model.model[1].copy()]
    first = [np.zeros_like(p) for p in params]; second = [np.zeros_like(p) for p in params]
    decode_w, decode_b = decoder[0][:, varying], decoder[1][varying]
    best = None; log = []
    for iteration in range(1, 1601):
        batch = rng.integers(0, len(start_ids), 128)
        current = z[start_ids[batch]].copy()
        tape = []
        a, b, w, bias = params
        for step in range(3):
            x = np.concatenate([current, model.events[events[step][batch]]], axis=1)
            t = np.tanh(x @ a + b)
            feature = np.concatenate([x, t], axis=1)
            current = current + feature @ w + bias
            target_ids = truth_ids[step][batch]
            g = 2*(current - z[target_ids])/(len(batch)*d*3)
            logits = 4*(current @ decode_w + decode_b - .5)
            probability = 1/(1+np.exp(-np.clip(logits, -30, 30)))
            g += .1*4*((probability-facts[target_ids][:, varying]) @ decode_w.T)/(len(batch)*varying.sum()*3)
            tape.append((x, t, feature, g))
        grads = [np.zeros_like(p) for p in params]
        carry = np.zeros_like(current)
        for x, t, feature, local in reversed(tape):
            g = carry + local
            grads[2] += feature.T @ g; grads[3] += g.sum(axis=0)
            gf = g @ w.T
            gt = gf[:, d+16:] * (1-t*t)
            grads[0] += x.T @ gt; grads[1] += gt.sum(axis=0)
            carry = g + gf[:, :d] + (gt @ a.T)[:, :d]
        norm = np.sqrt(sum(float((g*g).sum()) for g in grads))
        for p, g, m, v in zip(params, grads, first, second):
            g *= min(1., 1./max(norm, 1e-20))
            m *= .9; m += .1*g
            v *= .999; v += .001*g*g
            p -= .001*(m/(1-.9**iteration))/(np.sqrt(v/(1-.999**iteration))+1e-8)
        if iteration % 200 == 0:
            model.a, model.bias = params[0], params[1]
            model.model = (params[2].astype(np.float16).astype(np.float32), params[3])
            val = evaluate_transition(model, z, facts, targets, valid, decoder, varying)
            trace, _ = rollout(model, z, facts, targets, valid, decoder, varying, seed=17)
            quality = (trace['all_steps_exact_rate'], val['exact_state_rate'], -val['latent_rmse'])
            if best is None or quality > best[0]:
                best = (quality, [p.copy() for p in params], iteration)
            log.append(dict(iteration=iteration, one_step=val['exact_state_rate'],
                            whole_trace=trace['all_steps_exact_rate']))
            print('trained nonlinear', iteration, log[-1], flush=True)
    _, params, chosen = best
    model.a, model.bias = params[0], params[1]
    model.model = (params[2].astype(np.float16).astype(np.float32), params[3])
    return model, dict(validation_checkpoints=log, chosen_iteration=chosen,
                       training_steps=3, training_sequences=len(start_ids), hidden=hidden)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    states, facts, targets, train, valid, test = dataset()
    teacher_validation = validate_teacher(states, targets)
    varying = np.ptp(facts, axis=0) > 0
    mean = facts[train].mean(axis=0)
    _, singular, vt = np.linalg.svd(facts[train] - mean, full_matrices=False)
    rank = int((singular > singular[0] * 1e-6).sum())
    results = []
    for d in (16, 32, 64):
        # Learned dense encoder, fitted only on training structural states.
        basis = vt[:d].T
        scale = np.maximum(np.std((facts[train] - mean) @ basis, axis=0), .1)
        z = (((facts - mean) @ basis) / scale).astype(np.float16).astype(np.float32)
        decoder = ridge(z[train], facts[train], regularization=.001)
        record = dict(dimension=d, encoding_test=error(predict(z[test], decoder), facts[test], varying), models=[])
        sources, actions = np.where(train[:, None] & train[targets])
        for kind, hidden in [('linear', 0), ('bilinear', 0), ('nonlinear', 256), ('nonlinear', 768),
                             ('switched-linear', 0), ('switched-quadratic', 0)]:
            model = Transition(kind, d, hidden, np.random.default_rng(1701 + d + hidden))
            model.fit(z[sources], actions, z[targets[sources, actions]])
            val = evaluate_transition(model, z, facts, targets, valid, decoder, varying)
            held = evaluate_transition(model, z, facts, targets, test, decoder, varying)
            trace, events = rollout(model, z, facts, targets, test, decoder, varying)
            item = dict(kind=kind, hidden=hidden, parameters=model.parameter_count(), validation=val,
                        test=held, autonomous=trace)
            record['models'].append(item)
            print(d, kind, hidden, 'encode', round(record['encoding_test']['exact_state_rate'], 4),
                  'one-step', round(held['exact_state_rate'], 4), 'rollout', round(trace['all_steps_exact_rate'], 4), flush=True)
        results.append(record)
    # Fixed predeclared dimension, not chosen by held-out test accuracy.
    d = 32
    basis = vt[:d].T
    scale = np.maximum(np.std((facts[train]-mean)@basis, axis=0), .1)
    z = (((facts-mean)@basis)/scale).astype(np.float16).astype(np.float32)
    decoder = ridge(z[train], facts[train], regularization=.001)
    model, trained = train_nonlinear(z, facts, targets, train, valid, decoder, varying)
    trained['test'] = evaluate_transition(model, z, facts, targets, test, decoder, varying)
    trained['autonomous'], events = rollout(model, z, facts, targets, test, decoder, varying)
    initial = z[np.tile(np.flatnonzero(test), 4)]
    # Optional numeric GPU reproduction: inputs are real latents, not facts.
    np.savez(args.output / 'selected.npz', initial=initial, events=events, event_codes=model.events,
             a=model.a, bias=model.bias, w=model.model[0], out_bias=model.model[1],
             decoder_w=decoder[0], decoder_b=decoder[1])
    result = dict(scope='standalone finite constructor/equality teacher; no production takeover',
                  experiment_status='complete', semantic_takeover_accepted=False,
                  states=len(states), observables=facts.shape[1], varying_observables=int(varying.sum()),
                  training_covariance_rank=rank, train_states=int(train.sum()), validation_states=int(valid.sum()),
                  test_states=int(test.sum()), training_transitions=len(sources), event_types=17,
                  observed_native_runtime=False, gpu_execution=False, results=results,
                  teacher_validation=teacher_validation,
                  invariant_span_checks=[invariant_span(facts, targets, cutoff) for cutoff in (1e-7, 1e-8, 1e-9)],
                  trained_nonlinear=trained,
                  selected_by_validation=dict(dimension=d, hidden=model.hidden, checkpoint=trained['chosen_iteration']),
                  seconds=time.perf_counter()-start,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output / 'results.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results', 'trained_nonlinear')}, indent=2))


if __name__ == '__main__':
    main()
