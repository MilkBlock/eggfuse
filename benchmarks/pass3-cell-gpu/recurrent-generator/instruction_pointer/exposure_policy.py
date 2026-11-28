"""Frozen policies and named native ledgers. Only the historical Stream reads its own source anchor."""
import json
from collections import Counter
from time import perf_counter

import numpy as np
import torch

from cell_transaction import update_memory
from continuous_trials import instrument
from discrete_reference import Reference
from exposure_train import output
from exposure_worlds import world
from joint_cell_live import UniformDecoder
from prefix_train import make
from recursive_rollout import get_policy
from scaling_archive import directory
from scaling_eval import Sampling


class NamedPaths:
    def __init__(self):
        self.tokens = []

    def proofs_from_paths(self, stream, paths):
        refs = np.empty((len(paths), len(stream.order), 3), dtype=np.int64)
        for j, role in enumerate(stream.order):
            refs[:, role] = stream.port_refs(j)[paths[:, j]].numpy()
        self.tokens.extend((stream.rule, tuple(map(tuple, row.tolist()))) for row in refs)


class Historical:
    def __init__(self, a):
        self.a = a

    def prepare(self, w):
        pol = get_policy(self.a.data, w.dir, "free", "multi")
        self.rd, self.model = pol.reader, pol.model
        self.stream = Reference(original_order=True)
        self.stats = Counter()
        self.last_run = None
        self.remaining = []

    def observe_native_memory(self, frame, publication, repairs):
        update_memory(self.rd, frame, publication, repairs)
        self.frame = frame

    def propose(self, slots):
        sink = NamedPaths()
        self.stream.run_request_cap = slots
        self.stream.run_snapshot(self.frame, None, self.rd, self.model, sink,
                                 self.stats, perf_counter() + 120)
        return sink.tokens

    def generate(self, w, s, rng, slots):
        if self.last_run != s["run"]:
            self.remaining = self.propose(6)
            self.last_run = s["run"]
        cells, self.remaining = self.remaining[:slots], self.remaining[slots:]
        return cells


def policy(a, case, name, unique=True):
    n = make(a, "rel")
    w, align = world(a, n.actor, case)
    if name == "history":
        return Historical(a), w, align
    if name == "random":
        n = UniformDecoder()
    else:
        if "/" in name:
            group, tag = name.split("/")
            path = output(a) / group / (tag + ".pt")
        else:
            path = directory(a) / "fits" / (name + ".pt")
        if name.startswith("read-width-"):
            from foundation_fit import WideRead

            width = int(name.partition("/")[0].removeprefix("read-width-"))
            n.actor.next_read = WideRead(n.actor.next_read, width, jitter=0.0)
        n.load_state_dict(torch.load(path, weights_only=True))
        n.eval()
        instrument(n, "exact")
    return Sampling(n, 1., unique), w, align
