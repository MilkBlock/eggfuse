"""Blind value cubes, native free draws and conditional transfer after the singleton gate."""

import copy
import tarfile
from collections import defaultdict
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World
from partner_index_worlds import args
from token_embedding_study import save
from value_read_model import ValueRead
from value_read_train import SEEDS, SINGLE, STEPS, mode, output
from value_read_world import CUBES, SCHEMAS, field_pair, filler_values, instance, key


def models(a):
    nets = {}
    for arm in "ABC":
        for seed in SEEDS:
            for step in (0, SINGLE, STEPS):
                if step == 0 and seed != SEEDS[0]:
                    continue
                net = ValueRead(a, arm).eval()
                if step:
                    net.load_state_dict(
                        torch.load(
                            output(a) / f"{arm}-{seed}-{step}.pt", weights_only=True
                        )
                    )
                nets[arm, seed, step] = net
    return nets


class Observe:
    def __init__(self, net):
        self.net = net
        self.entry = None

    def prepare(self, w):
        self.net.prepare(w)

    def generate(self, w, s, rng, slots):
        draws = self.net.generate(w, s, rng, slots)
        if w.root in s["menu"]:
            self.entry = (s, draws)
        return draws


def flip_stats(rows):
    pairs = defaultdict(dict)
    for r in rows:
        pos = field_pair(r["schema"][0])[1]
        bits = r["bits"]
        k = (*r["schema"], r["pool"], tuple(bits[:pos] + bits[pos + 1 :]))
        pairs[k][bits[pos]] = r
    wins = 0
    for pair in pairs.values():
        a, b = pair[0], pair[1]
        assert a["gold"] != b["gold"] and a["refs"] == b["refs"]
        wins += a["gold_margin"] > 0 and b["gold_margin"] > 0
    return wins, len(pairs)


@torch.no_grad()
def evaluate(a, wide=False):
    if wide and mode() != "rich":
        raise ValueError("the independent wide follow-up uses the rich checkpoint")
    saved = output(a) / "wide" if wide else output(a)
    saved.mkdir(exist_ok=True, parents=True)
    with (
        tarfile.open(saved / "blind-native.tar.gz", "w:gz", compresslevel=1)
        if mode() != "pilot"
        else nullcontext()
    ) as archive:
        evaluate_states(a, wide, saved, archive)


def evaluate_states(a, wide, saved, archive):
    train_pools = range(72001, 72033) if mode() == "rich" else range(71001, 71007)
    trained_values = set().union(*(set(filler_values(p)) for p in train_pools))
    nets = models(a)
    actor = next(iter(nets.values())).actor
    train_rec = {}
    sigs = set()
    for schema in SCHEMAS:
        w = World(a.out / "worlds" / key(schema, 71001, CUBES[0]), actor)
        train_rec[schema] = w.prog["recipe"]["sha256"]
        sigs.update(digest(w))
    rows = []
    runs = []
    layout = []
    def cube(label, schema, pool, depth, distract, live, novel):
        assert trained_values.isdisjoint(filler_values(pool))
        states = {}
        sig = None
        for bits in CUBES:
            if archive is None:
                w = instance(a, actor, schema, pool, bits, depth, distract)
            else:
                scratch = TemporaryDirectory()
                temp = copy.copy(a)
                temp.out = Path(scratch.name)
                w = instance(temp, actor, schema, pool, bits, depth, distract)
                archive.add(w.dir, arcname=w.dir.name)
            if sig is None:
                sig = digest(w)
                if novel:
                    assert not sigs.intersection(sig)
                elif not distract:
                    assert w.prog["recipe"]["sha256"] == train_rec[schema]
            assert digest(w) == sig
            entry, targets = native(a, w, teacher="higher")[0]
            states[bits] = entry
            (gold,) = [(t, rs) for t, rs in targets if t >= w.primitives]
            tid, refs = gold
            for (arm, seed, step), net in nets.items():
                net.prepare(w)
                m = net.state(w, entry)
                hp = m["lp"][
                    [m["menu"].index(i) for i in range(w.primitives, len(w.layouts))]
                ]
                margin = float(hp[tid - w.primitives] - hp[1 - (tid - w.primitives)])
                bind = float(net.address(w, m, tid, [])[m["pos"][refs[0]]].exp())
                rows.append(
                    {
                        "label": label,
                        "schema": list(schema),
                        "pool": pool,
                        "bits": list(bits),
                        "v": arm,
                        "seed": seed,
                        "step": step,
                        "gold": tid - w.primitives,
                        "refs": refs,
                        "gold_margin": margin,
                        "p_pair": float(hp.softmax(0)[tid - w.primitives]),
                        "p_template": float(hp[tid - w.primitives].exp()),
                        "p_bind": bind,
                        "p_full": float((-net.token_loss(w, m, gold)).exp()),
                    }
                )
                net.static_cache.clear()
            if live:
                configs = [
                    k
                    for k in nets
                    if k[2] == STEPS or (label == "first" and k[2] == SINGLE)
                ]
                for draw in (193, 827):
                    for block in (0, 1):
                        order = (
                            configs
                            if (block + (draw == 827)) % 2 == 0
                            else reversed(configs)
                        )
                        for arm, seed, step in order:
                            net = nets[arm, seed, step]
                            net.static_cache.clear()
                            spy = Observe(net)
                            result = native(a, w, policy=spy, seed=draw)
                            s, out = spy.entry
                            # This post-execution check scores the physical address chosen by the
                            # policy; each program has one Seed in its table at the root window.
                            (actual_ref,) = [
                                p[0] for p in s["ports"] if p[3] == w.tabs.index("Seed")
                            ]
                            hits = sum(t == tid and r == (actual_ref,) for t, r in out)
                            runs.append(
                                dict(
                                    label=label,
                                    schema=list(schema),
                                    pool=pool,
                                    bits=list(bits),
                                    v=arm,
                                    seed=seed,
                                    step=step,
                                    draw=draw,
                                    block=block,
                                    hits=hits,
                                    slots=len(out),
                                    **result,
                                )
                            )
            if archive is not None:
                scratch.cleanup()
        # All pairs are real native pairs. No unrelated row, receipt, address or field may change.
        j = field_pair(schema[0])[1]
        for bits, s in states.items():
            if bits[j]:
                continue
            other = list(bits)
            other[j] = 1
            u = states[tuple(other)]
            assert {k: v for k, v in s.items() if k != "ports"} == {
                k: v for k, v in u.items() if k != "ports"
            }
            diffs = [
                (p, q) for p, q in zip(s["ports"], u["ports"], strict=True) if p != q
            ]
            ((p, q),) = diffs
            assert (
                p[:4] == q[:4]
                and p[5:] == q[5:]
                and [
                    k for k, (x, y) in enumerate(zip(p[4], q[4], strict=True)) if x != y
                ]
                == [j]
            )
        layout.append(
            {
                "label": label,
                "schema": list(schema),
                "pool": pool,
                "recipe": w.prog["recipe"]["sha256"],
                "higher": sig,
            }
        )
        save(saved / "blind.json", rows)
        save(saved / "native.json", runs)
        save(saved / "layouts.json", layout)

    if wide:
        if not (output(a) / "gate.json").is_file():
            raise ValueError("run the primary evaluation before the follow-up")
        for pool in range(100101, 100133):
            cube("first-wide", SCHEMAS[0], pool, 1, False, False, False)
        return
    offset = 0 if mode() == "pilot" else 10000
    for pool in range(81001 + offset, 81009 + offset):
        cube("first", SCHEMAS[0], pool, 1, False, pool == 81001 + offset, False)
    allowed = []
    for v in "ABC":
        ok = True
        for seed in SEEDS:
            r = [
                x
                for x in rows
                if x["v"] == v and x["seed"] == seed and x["step"] == SINGLE
            ]
            wins, n = flip_stats(r)
            ok = ok and wins / n >= 0.9 and np.mean([x["p_pair"] for x in r]) >= 0.9
        if ok:
            allowed.append(v)
    save(
        saved / "gate.json",
        {
            "passed": allowed,
            "criterion": "420-update checkpoint: both seeds >=90% two-sided flips and >=0.90 mean pair probability",
        },
    )
    for schema in SCHEMAS:
        for pool in range(81011 + offset, 81015 + offset):
            cube("factorial", schema, pool, 1, False, pool == 81011 + offset, False)
    # Measure independent execution in larger memories even if transfer is deferred.
    for schema in (SCHEMAS[0], SCHEMAS[-1]):
        cube("distractor", schema, 81020 + offset, 1, True, True, False)
    if allowed:
        for g, o in ((0, 0), (0, 1), (1, 0), (1, 1)):
            for label, schema, depth in (
                ("wiring", (2, g, o), 1),
                ("deep", (0, g, o), 3),
            ):
                cube(label, schema, 81025 + offset, depth, False, True, True)
    print("gate", allowed, "native runs", len(runs), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    evaluate(a, wide=a.task == "evaluate")
