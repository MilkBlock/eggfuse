"""Numerical replay of the previously selected dense tanh model, no repair."""
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


class Prior:
    def __init__(self, path):
        self.p = dict(np.load(path))
        spec = importlib.util.spec_from_file_location('prior_teacher', ROOT/'benchmarks/cell-real-state/study.py')
        teacher = importlib.util.module_from_spec(spec); spec.loader.exec_module(teacher)
        _, facts, _, train, _, test = teacher.dataset()
        self.mean = facts[train].mean(axis=0)
        _, _, vt = np.linalg.svd(facts[train]-self.mean, full_matrices=False)
        d = self.p['initial'].shape[1]
        self.basis = vt[:d].T
        self.scale = np.maximum(np.std((facts[train]-self.mean)@self.basis, axis=0), .1)
        if not np.array_equal(self.encode(facts[np.tile(np.flatnonzero(test), 4)]), self.p['initial']):
            raise ValueError('prior encoder reconstruction differs from saved initial states')

    def encode(self, facts):
        return (((facts-self.mean)@self.basis)/self.scale).astype(np.float16).astype(np.float32)

    def step(self, latent, actions):
        base = np.concatenate([latent, self.p['event_codes'][actions]], axis=1)
        a = self.p['a'].astype(np.float16).astype(np.float32)
        hidden = np.tanh(base.astype(np.float16).astype(np.float32)@a+self.p['bias'])
        features = np.concatenate([base, hidden], axis=1).astype(np.float16).astype(np.float32)
        return (latent+features@self.p['w']+self.p['out_bias']).astype(np.float16).astype(np.float32)

    def decode(self, latent):
        return latent.astype(np.float16).astype(np.float32)@self.p['decoder_w']+self.p['decoder_b']


def load_adapter(path):
    return Prior(path)
