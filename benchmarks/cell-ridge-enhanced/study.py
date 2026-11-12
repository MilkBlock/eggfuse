"""Long-rollout ridge and bounded radial features; standalone finite teacher."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ridge_teacher', ROOT/'benchmarks/cell-real-state/study.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def weighted_ridge(x, y, weight, reg):
    x, y = x.astype(np.float64), y.astype(np.float64)
    weight = weight / weight.mean()
    mx, my = np.average(x, axis=0, weights=weight), np.average(y, axis=0, weights=weight)
    xc = (x-mx)*np.sqrt(weight[:, None])
    yc = (y-my)*np.sqrt(weight[:, None])
    w = np.linalg.solve(xc.T@xc+reg*np.eye(x.shape[1]), xc.T@yc)
    b = my-mx@w
    assert np.isfinite(w.astype(np.float16)).all()
    return w.astype(np.float16).astype(np.float32), b.astype(np.float32)


class Model:
    def __init__(self, kind, centers, bound):
        self.kind, self.centers, self.bound = kind, centers, bound
        self.i, self.j = np.triu_indices(32)

    def features(self, z):
        if self.kind == 'quadratic':
            return np.concatenate([z, z[:, self.i]*z[:, self.j]], axis=1)
        # Dense real projection plus smooth bounded nonlinearity. All centers
        # come from training states; no nearest-center selection or decoding.
        distance = np.maximum((z*z).sum(1)[:, None] + (self.centers*self.centers).sum(1)
                              - 2*z@self.centers.T, 0)
        return np.concatenate([z, np.exp(-distance/32)], axis=1)

    def fit(self, x, actions, y, weights, reg):
        f = self.features(x)
        self.bank = [weighted_ridge(f[actions == a], (y-x)[actions == a], weights[actions == a], reg)
                     for a in range(17)]

    def step(self, z, actions):
        f = self.features(z)
        result = z.copy()
        for a, bank in enumerate(self.bank):
            keep = actions == a
            result[keep] += t.predict(f[keep], bank)
        return np.clip(result, -self.bound, self.bound).astype(np.float16).astype(np.float32)

    def save(self, path, mean, basis, scale, decoder):
        np.savez(path, kind=self.kind, centers=self.centers, bound=self.bound,
                 w=np.stack([p[0] for p in self.bank]), bias=np.stack([p[1] for p in self.bank]),
                 mean=mean, basis=basis, scale=scale, decoder_w=decoder[0], decoder_b=decoder[1])


class Adapter:
    def __init__(self, path):
        self.p = dict(np.load(path))
        self.model = Model(str(self.p['kind']), self.p['centers'], self.p['bound'])
        self.model.bank = list(zip(self.p['w'], self.p['bias']))

    def encode(self, facts):
        p = self.p
        return (((facts-p['mean'])@p['basis'])/p['scale']).astype(np.float16).astype(np.float32)

    def step(self, z, actions):
        return self.model.step(z, actions)

    def decode(self, z):
        return t.predict(z, (self.p['decoder_w'], self.p['decoder_b']))


def load_adapter(path):
    return Adapter(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    states, facts, targets, train, valid, test = t.dataset()
    mean = facts[train].mean(0)
    _, _, vt = np.linalg.svd(facts[train]-mean, full_matrices=False)
    basis = vt[:32].T
    scale = np.maximum(((facts[train]-mean)@basis).std(0), .1)
    z = (((facts-mean)@basis)/scale).astype(np.float16).astype(np.float32)
    decoder = t.ridge(z[train], facts[train], .001)
    bound = np.maximum(np.abs(z[train]).max(0)*1.25, 1.)
    varying = np.ptp(facts[train], axis=0) > 0
    src, act = np.where(train[:, None] & train[targets])
    dst = targets[src, act]
    columns = [t.PAIRS.index(pair) for pair in t.BASE_PAIRS]

    def weights(ids, actions, dest, multiplier):
        feedback = (actions >= 15) & (facts[ids][:, columns] != facts[dest][:, columns]).any(1)
        return np.where(feedback, multiplier, 1.).astype(np.float64)

    # Freeze all trajectories before any fit; all intermediates remain train.
    rng = np.random.default_rng(824)
    allowed = [np.flatnonzero(train[targets[i]]) for i in range(len(states))]
    starts = rng.choice(np.flatnonzero(train), 1024)
    ids = starts.copy()
    trace = []
    for _ in range(8):
        actions = np.array([rng.choice(allowed[i]) for i in ids])
        dest = targets[ids, actions]
        assert train[ids].all() and train[dest].all()
        trace.append((ids.copy(), actions, dest))
        ids = dest
    center_ids = rng.permutation(np.flatnonzero(train))
    configs = [('quadratic', 0, 1.), ('quadratic', 0, 8.), ('radial', 128, 8.), ('radial', 256, 8.)]
    # Fixed budget: 4 representations x 2 regularizers x 5 checkpoints.
    log, best = [], None
    for kind, count, multiplier in configs:
        for reg in (1., 10.):
            model = Model(kind, z[center_ids[:count]], bound)
            model.fit(z[src], act, z[dst], weights(src, act, dst, multiplier), reg)
            for iteration in range(5):
                val = t.evaluate_transition(model, z, facts, targets, valid, decoder, varying)
                rollout, _ = t.rollout(model, z, facts, targets, valid, decoder, varying, seed=17)
                row = dict(kind=kind, centers=count, feedback_weight=multiplier, reg=reg, iteration=iteration,
                           validation_one_step=val['exact_state_rate'], validation_trace=rollout['all_steps_exact_rate'])
                log.append(row)
                print(json.dumps(row), flush=True)
                quality = (row['validation_trace'], row['validation_one_step'], -val['latent_rmse'])
                if best is None or quality > best[0]:
                    best = (quality, row)
                    model.save(args.output/'model.npz', mean, basis, scale, decoder)
                if iteration == 4:
                    break
                xs, actions_list, ys = [z[src]], [act], [z[dst]]
                ws = [weights(src, act, dst, multiplier)]
                current = z[starts].copy()
                for ids, actions, dest in trace:
                    xs.append(current.copy()); actions_list.append(actions); ys.append(z[dest])
                    ws.append(weights(ids, actions, dest, multiplier))
                    current = model.step(current, actions)
                model.fit(np.concatenate(xs), np.concatenate(actions_list), np.concatenate(ys), np.concatenate(ws), reg)
    adapter = load_adapter(args.output/'model.npz')
    held = t.evaluate_transition(adapter.model, z, facts, targets, test, decoder, varying)
    rollout, _ = t.rollout(adapter.model, z, facts, targets, test, decoder, varying)
    result = dict(scope='standalone finite teacher; no native takeover or GPU speed claim',
                  selection=best[1], validation=log, test=held, autonomous=rollout,
                  train_edges=len(src), train_trajectory_count=len(starts), train_trajectory_steps=8,
                  feedback_train_edges=int((weights(src, act, dst, 8) > 1).sum()),
                  feature_width=adapter.model.features(z[:1]).shape[1],
                  transition_parameters=sum(w.size+b.size for w, b in adapter.model.bank),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  teacher_sha256=hashlib.sha256(Path(t.__file__).read_bytes()).hexdigest())
    (args.output/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print('SELECTED', best[1], 'TEST', held['exact_state_rate'], 'TRACE', rollout['all_steps_exact_rate'], flush=True)


if __name__ == '__main__':
    main()
