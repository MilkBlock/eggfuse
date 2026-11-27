"""Fixed-capacity generation with exact-view reuse and reversible named-leaf discount."""

from collections import Counter
from contextlib import contextmanager

import torch
from time import perf_counter

from competition_draw import Page


def named_path(page, token):
    tid, refs = token
    m, w = page.m, page.w
    rid = w.layouts[tid][0][0]
    if (
        tid not in m["menu"]
        or rid not in page.roots
        or any(r not in m["pos"] for r in refs)
    ):
        return None
    key = ("root", None, None, ())
    path = []
    while key[0] != "emit":
        stage, _, _, prefix = key
        if key not in page.base:
            page.base[key] = page.transition(key)
        transition = page.base[key]
        if transition is None:
            return None
        if stage == "root":
            index = page.roots.index(rid)
        elif stage == "variant":
            index = m["families"][rid].index(m["menu"].index(tid))
        else:
            index = m["pos"][refs[len(prefix)]]
        p, child = transition
        if p[index] == 0:
            return None
        path.append((key, index))
        key = child(index)
    return path


class Stream:
    def __init__(self, net, mode, *, incremental=True):
        if mode not in ("A", "B", "C", "iid"):
            raise ValueError(f"unknown stream mode {mode}")
        self.net = net
        self.incremental = incremental
        self.memory_cache = None
        self.mode = mode
        self.count = Counter()
        self.time = Counter()
        self.view = None
        self.previous = ()
        self.publication = 0

    def prepare(self, w):
        start = perf_counter()
        self.view = None
        self.previous = ()
        self.net.prepare(w)
        self.time["static_prepare"] += perf_counter() - start

    @contextmanager
    def inference_session(self):
        from cell_kv_model import CellKV
        from incremental_kv import InferenceCache

        n = self.net
        if (not self.incremental or not isinstance(n, CellKV) or n.training
                or torch.is_grad_enabled() or type(n).instance_embedding is not CellKV.instance_embedding
                or "published_kv" in vars(n) or "response_kv" in vars(n)):
            yield
            return
        self.memory_cache = InferenceCache(n)
        try:
            yield
        finally:
            del n.published_kv, n.response_kv
            self.memory_cache = None

    def observe_publication(self, frame):
        # Every new native publication invalidates all cached neural distributions.
        self.publication += 1
        self.page = None

    def generate(self, w, s, rng, slots):
        self.count["slots"] += slots
        if not s["menu"]:
            self.previous = ()
            return []
        # Instances.snapshot's only varying input within one publication is the
        # append-only request receipt buffer. Suffix acknowledgements also count.
        view = self.publication, len(s["request_receipts"])
        start = perf_counter()
        if self.mode in ("A", "iid") or self.view != view:
            self.page = Page(self.net, w, s)
            self.adjusted = {}
            self.count["state_encodes"] += 1
            self.time["state"] += perf_counter() - start
            start = perf_counter()
            if self.mode == "C" and self.previous:
                for token in dict.fromkeys(self.previous):
                    path = named_path(self.page, token)
                    if path is not None:
                        self.page.set_leaf_factor(path, self.adjusted, 0.25)
                        self.count["discounted_names"] += 1
            self.time["rebase"] += perf_counter() - start
        else:
            self.count["exact_view_reuse"] += 1
        self.view = view
        start = perf_counter()
        cells = [
            t
            for t in self.page.draws(
                rng, slots, self.mode != "iid", adjusted=self.adjusted
            )
            if t is not None
        ]
        self.time["draw"] += perf_counter() - start
        self.previous = cells
        return cells
