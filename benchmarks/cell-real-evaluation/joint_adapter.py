"""Fixed joint model precision diagnostics; no training or state correction."""
from pathlib import Path
import importlib.util
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('joint_candidate', ROOT/'benchmarks/cell-real-joint/study.py')
joint = importlib.util.module_from_spec(spec); spec.loader.exec_module(joint)


class Adapter:
    def __init__(self, path, precision):
        if precision not in ('fp32', 'fp16weights', 'fp16activations'):
            raise ValueError('precision')
        self.precision = precision
        self.model = joint.Model.load(path, half=precision != 'fp32')
        if precision == 'fp16activations':
            self.model.codes = self.half(self.model.codes)

    @staticmethod
    def half(x):
        return x.astype(np.float16).astype(np.float32)

    def encode(self, facts):
        z = self.model.encode(facts)
        return self.half(z) if self.precision == 'fp16activations' else z

    def step(self, z, actions):
        if self.precision != 'fp16activations':
            return self.model.step(z, actions)
        p = self.model.p
        z = self.half(z)
        x = np.concatenate([z, self.model.codes[actions]], axis=1)
        hidden = self.half(np.tanh(x@p[2]+p[3]))
        return self.half(np.tanh(z+hidden@p[4]+p[5]))

    def decode(self, z):
        return self.model.decode(z)


def load_adapter(path, precision='fp32'):
    return Adapter(path, precision)
