"""Follow-up fixed-budget ridge study retaining prior algebraic anchors."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from study import Model as Base, t, weighted_ridge


class Model(Base):
    def features(self, z):
        if self.kind == 'cubic':
            return np.concatenate([z, (1+z@self.centers.T/32)**3], axis=1)
        return super().features(z)

    def fit(self, x, actions, y, weights, reg):
        f = self.features(x)
        self.bank = []
        # Training-only scaling makes the ridge penalty comparable across
        # feature coordinates. Fold scaling into weights: no extra runtime op.
        for a in range(17):
            keep = actions == a
            scale = np.maximum(f[keep].std(axis=0), .05)
            w, b = weighted_ridge(f[keep]/scale, (y-x)[keep], weights[keep], reg)
            self.bank.append(((w/scale[:, None]).astype(np.float16).astype(np.float32), b))


class Adapter:
    def __init__(self, path):
        self.p = dict(np.load(path))
        p = self.p
        self.model = Model(str(p['kind']), p['centers'], p['bound'])
        self.model.bank = list(zip(p['w'], p['bias']))

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
    states, facts, target, train, valid, test = t.dataset()
    mean = facts[train].mean(0)
    _, _, vt = np.linalg.svd(facts[train]-mean, full_matrices=False)
    basis = vt[:32].T
    scale = np.maximum(((facts[train]-mean)@basis).std(0), .1)
    z = (((facts-mean)@basis)/scale).astype(np.float16).astype(np.float32)
    decoder = t.ridge(z[train], facts[train], .001)
    bound = np.maximum(np.abs(z[train]).max(0)*1.25, 1.)
    varying = np.ptp(facts[train], axis=0) > 0
    src, act = np.where(train[:, None] & train[target])
    dst = target[src, act]
    # Retain exactly the original composition sample and reverse-order anchors.
    rng = np.random.default_rng(441)
    allowed = [np.flatnonzero(train[target[s]]) for s in range(len(z))]
    second = np.array([rng.choice(allowed[d]) for d in dst])
    end = target[dst, second]
    ok = train[target[src, second]]
    assert train[end].all() and np.array_equal(target[target[src[ok], second[ok]], act[ok]], end[ok])
    center_ids = np.random.default_rng(824).permutation(np.flatnonzero(train))
    # Fixed follow-up: three feature families, two regularizers, seven rounds.
    configs = [('quadratic', 0), ('radial', 256), ('cubic', 256)]
    best, logs = None, []
    for kind, count in configs:
        for reg in (1., 10.):
            model = Model(kind, z[center_ids[:count]], bound)
            model.fit(z[src], act, z[dst], np.ones(len(src)), reg)
            for iteration in range(7):
                val = t.evaluate_transition(model, z, facts, target, valid, decoder, varying)
                trace, _ = t.rollout(model, z, facts, target, valid, decoder, varying, seed=17)
                row = dict(kind=kind, centers=count, reg=reg, iteration=iteration,
                           validation_one_step=val['exact_state_rate'], validation_trace=trace['all_steps_exact_rate'])
                logs.append(row); print(json.dumps(row), flush=True)
                quality = (row['validation_trace'], row['validation_one_step'], -val['latent_rmse'])
                if best is None or quality > best[0]:
                    best = (quality, row)
                    model.save(args.output/'model.npz', mean, basis, scale, decoder)
                if iteration == 6:
                    break
                predicted = model.step(z[src], act)
                other = model.step(z[src[ok]], second[ok])
                x = np.concatenate([z[src], predicted, predicted, other])
                a = np.concatenate([act, act, second, act[ok]])
                y = np.concatenate([z[dst], z[dst], z[end], z[end[ok]]])
                model.fit(x, a, y, np.ones(len(a)), reg)
    adapter = load_adapter(args.output/'model.npz')
    held = t.evaluate_transition(adapter.model, z, facts, target, test, decoder, varying)
    trace, _ = t.rollout(adapter.model, z, facts, target, test, decoder, varying)
    result = dict(scope='standalone finite teacher; follow-up after long-rollout experiment',
                  selection=best[1], validation=logs, test=held, autonomous=trace,
                  feature_width=adapter.model.features(z[:1]).shape[1],
                  transition_parameters=sum(w.size+b.size for w, b in adapter.model.bank),
                  source_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest()
                                 for n in ('study.py', 'anchored.py')},
                  teacher_sha256=hashlib.sha256(Path(t.__file__).read_bytes()).hexdigest())
    (args.output/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print('SELECTED', best[1], 'TEST', held['exact_state_rate'], 'TRACE', trace['all_steps_exact_rate'], flush=True)


if __name__ == '__main__':
    main()
