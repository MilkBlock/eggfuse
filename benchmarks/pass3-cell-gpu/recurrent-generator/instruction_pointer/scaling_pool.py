"""Program-isolated complete-Token pools. Outer EggCC is inaccessible to the sampler."""

import gzip
import json
import pickle
import random
from collections import Counter, defaultdict
from pathlib import Path

from competition_egg import egg
from int_parameters import digest
from joint_cell_train import build
from scaling_archive import Archive, directory


class Pool:
    def __init__(self, a, n, extra_egg=False):
        self.arch = Archive(a, n.actor)
        self.base = {}
        self.val = []
        self.records = {}
        self.locs = defaultdict(list)
        self.effects = {}
        self.collections = defaultdict(list)
        self.freq = Counter()
        self.programs = set()
        d = directory(a)
        manifest = d / "archive.jsonl"
        bank = list(map(json.loads, manifest.read_text().splitlines()))
        expected = sum(
            len(list((self.arch.root / f / "buffer").glob("*.json.gz")))
            for f in ("transition-credit-1127", "credit-scaling-1126")
        )
        if len(bank) != expected:
            raise ValueError("native replay manifest incomplete")
        self.catalogue_digest = digest([(r["path"], r["sha"]) for r in bank])
        for r in bank:
            for idx, phase, sh, count, _ in r["states"]:
                key = r["program"], sh
                self.locs[key].append((r["path"], idx, phase))
                self.freq[key] += count
                if key not in self.records:
                    src = "autonomous" if "-2-" in Path(r["path"]).name else "shuffle"
                    self.add(key, src)
        # The outer program never supplies labels. loopfact and two complete
        # foundation programs form internal validation including every related prefix.
        validation_path = egg(a, "loopfact")[0]
        groups = build(a, "sum-divisors", n)
        for src, rows in groups.items():
            for w, s, ts in rows:
                self.add_base(
                    src,
                    w,
                    s,
                    ts,
                    w.dir == validation_path
                    or w.dir.name.startswith("foundation-252205-"),
                )
        extra = d / "transitions.pkl.gz"
        if extra.exists():
            from state_transition_corpus import world

            with gzip.open(extra, "rb") as f:
                data = pickle.load(f)
            for i, rows in data.items():
                w = world(a, n.actor, i, True)
                for s, labels in rows:
                    key = self.add_base("continuous", w, s, labels, i >= 10)
                    self.effects[key] = {t: digest(g) for t, g in labels.items()}
        if extra_egg:
            from continuous_trials import setup

            _, w, _ = setup(a, "fact")
            w.scaling_id = digest([w.prog, w.layouts])
            with gzip.open(d / "fact-rollouts.pkl.gz", "rb") as f:
                for s, targets in pickle.load(f):
                    self.add_base("egg_rollout", w, s, targets, False)
        # Base sources can observe the same state. Merge all verified names.
        self.keys = list(self.records)
        self.validation_keys = {k for k, _, _, _ in self.val}
        if self.validation_keys.intersection(self.keys):
            raise ValueError("state leak")
        if {k[0] for k in self.validation_keys} & {k[0] for k in self.keys}:
            raise ValueError("program leak")

    def add(self, key, source):
        self.records[key] = source
        self.collections[source].append(key)
        self.programs.add(key[0])

    def add_base(self, src, w, s, targets, validation):
        if not hasattr(w, "scaling_id"):
            import hashlib

            w.scaling_id = hashlib.sha256(
                (w.dir / "program.json").read_bytes()
            ).hexdigest()
        key = w.scaling_id, digest(s)
        if validation:
            self.val.append((key, w, s, sorted(set(targets))))
        else:
            if key not in self.base:
                self.base[key] = (w, s, set())
                self.add(key, src)
            self.base[key][2].update(targets)
            self.freq[key] += len(targets)
        return key

    def row(self, key):
        if key in self.base:
            w, s, ts = self.base[key]
            return w, s, sorted(ts)
        ts = set()
        for path, i, phase in self.locs[key]:
            w, s, names, _ = self.arch.rows(path)[i, phase]
            ts.update(names)
        return w, s, sorted(ts)


class Sampler:
    def __init__(self, pool, seed, cfg):
        self.pool, self.cfg, self.rng = pool, cfg, random.Random(seed)
        self.keys = pool.keys.copy()
        self.rng.shuffle(self.keys)
        self.keys = self.keys[: cfg.get("state_limit", len(self.keys))]
        self.groups = defaultdict(list)
        for k in self.keys:
            self.groups[pool.records[k]].append(k)
        self.weights = [pool.freq[k] for k in self.keys]
        import itertools

        self.cum = list(itertools.accumulate(self.weights))
        self.retention = 0.25
        self.ranks = {}
        if cfg.get("curriculum", "all") != "all":
            with gzip.open(directory(pool.arch.a) / "difficulty.pkl.gz", "rb") as f:
                dims = pickle.load(f)
            from bisect import bisect_right

            columns = [sorted(dims[k][j] for k in self.keys) for j in range(7)]
            self.ranks = {
                k: sum(
                    bisect_right(c, v) / len(c)
                    for c, v in zip(columns, dims[k], strict=True)
                )
                / len(columns)
                for k in self.keys
            }
            order = sorted(self.keys, key=self.ranks.get)
            self.ranks = {k: i / len(order) for i, k in enumerate(order)}

    def sample_key(self):

        mode = self.cfg.get("sampling", "mixed")
        if mode == "trajectory":
            key = self.rng.choices(self.keys, cum_weights=self.cum, k=1)[0]
        elif mode in ("state", "effect"):
            key = self.rng.choice(self.keys)
        else:
            sources = list(self.groups)
            weights = {
                "shuffle": 3,
                "autonomous": 4,
                "foundation": 1,
                "continuous": 1,
                "branch": 1,
                "teacher": 1,
                "egg_rollout": 2,
            }
            if mode == "teacher-self":
                sources = [
                    s
                    for s in sources
                    if s in ("teacher", "autonomous", "branch", "shuffle")
                ]
            key = self.rng.choice(
                self.groups[self.rng.choices(sources, [weights[s] for s in sources])[0]]
            )
        return key

    def next(self, progress):
        mode = self.cfg.get("sampling", "mixed")
        key = self.sample_key()
        if self.ranks:
            stage = min(2, int(progress * 3))
            curriculum = self.cfg["curriculum"]
            threshold = (stage + 1) / 3
            if (
                curriculum in ("retain", "adaptive")
                and self.rng.random() < self.retention
            ):
                threshold = 1 / 3
            lo = stage / 3 if curriculum == "strict" else 0.0
            while not lo <= self.ranks[key] < threshold:
                key = self.sample_key()
        w, s, targets = self.pool.row(key)
        if not targets:
            raise ValueError("unverified empty target group")
        if mode == "effect" and key in self.pool.effects:
            groups = defaultdict(list)
            for t in targets:
                groups[self.pool.effects[key][t]].append(t)
            targets = [self.rng.choice(g) for g in groups.values()]
        if self.cfg.get("block"):
            weights = None
            if mode == "trajectory" and key in self.pool.locs:
                visits = Counter()
                for path, i, phase in self.pool.locs[key]:
                    visits.update(self.pool.arch.rows(path)[i, phase][2])
                weights = [visits[t] for t in targets]
            targets = self.rng.choices(targets, weights=weights, k=self.cfg["block"])
        self.rng.shuffle(targets)
        limit = self.cfg.get("target_limit")
        if limit:
            targets = sorted(targets)[:limit]
            self.rng.shuffle(targets)
        return key, w, s, targets
