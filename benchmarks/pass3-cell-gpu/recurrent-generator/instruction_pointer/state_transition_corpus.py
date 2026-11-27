"""Fork the native driver from exact autonomous prefixes. Offline labels only."""

import os
import pickle

import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from competition_corpus import candidates, rowskey
from competition_draw import Policy
from competition_egg import network
from partner_index_worlds import args
from value_read_world import filler_values, program


def folder(a):
    d = a.out / "state-transition"
    d.mkdir(parents=True, exist_ok=True)
    return d


def world(a, actor, index, train):
    pool = (310000 if train else 720000) + index
    depth = 1 + index % 2 if train else 3
    source = program((index % 2, index // 2 % 2, index % 2), pool, (0, 0, 1), depth)
    source = source.replace("(rule ((Seed x y z))", "(rule ((Ready x y z))")
    vals = filler_values(pool + 932)
    lines = [
        "(relation Ready (i64 i64 i64))",
        "(relation Stamp (i64))",
        "(relation Mark (i64))",
        "(relation Empty (i64))",
        "(rule ((Seed x y z)) ((Ready x y z)) :ruleset root)",
        "(rule ((Seed x y z)) ((Stamp x)) :ruleset root)",
        "(rule () ((Mark 17)) :ruleset root)",
        "(rule ((Seed x y z) (Ready u v w)) ((Empty (+ x u))) :ruleset root)",
        f"(Seed {vals[0]} {vals[1]} {vals[0]})",
    ]
    source = source.replace("(ruleset root)", "(ruleset root)\n" + "\n".join(lines))
    source = source.replace(
        "(run-schedule (run root)", "(run-schedule (run root) (run root) (run root)"
    )
    return World(compile_world(a, f"transition-{pool}-{depth}", source), actor)


class Replay:
    def __init__(self, prefix, actions):
        self.prefix, self.actions, self.i = prefix, actions, 0

    def prepare(self, w):
        pass

    def generate(self, w, state, rng, slots):
        i = self.i
        self.i += 1
        if i < len(self.prefix):
            expected, decisions, _ = self.prefix[i]
            if state != expected:
                raise ValueError("state differs on replay")
            return decisions
        return self.actions if i == len(self.prefix) else []


def replay(a, w, seed, prefix, actions, reference=None):
    log, publications = [], []
    result = native(
        a,
        w,
        seed=seed,
        slots=max([6, len(actions), *(len(batch) for _, batch, _ in prefix)]),
        policy=Replay(prefix, actions),
        receipt_log=log,
        publication_log=publications,
        reference=reference,
    )
    if log[: len(prefix)] != prefix or len(log) <= len(prefix):
        raise ValueError("native prefix response mismatch")
    return result, log, publications


def verify(a, w, seed, prefix, reference=None):
    empty, log, pubs = replay(a, w, seed, prefix, [], reference)
    state = log[len(prefix)][0]
    base = rowskey(empty)
    labels = {}
    for token in candidates(w, state):
        result, observed, _ = replay(a, w, seed, prefix, [token], reference)
        s, _, answers = observed[len(prefix)]
        assert s == state
        uid, status, *_rest = answers[0]
        output = rowskey(result)
        complete = token[0] < w.primitives or uid in result["completed_owners"]
        gain = tuple(sorted(output - base))
        labels[token] = {
            "gain": gain,
            "lost": tuple(sorted(base - output)),
            "positive": not status and complete and base < output,
            "complete": complete,
            "receipt": answers[0],
        }
    return {
        "state": state,
        "labels": labels,
        "baseline": base,
        "publication": pubs[len(prefix)],
    }


def collect(a, index, train):
    d = folder(a)
    path = d / f"{'train' if train else 'test'}-{index}.pkl"
    if path.exists():
        return
    net = network(a, "B", (71, 113)[index % 2])
    w = world(a, net.actor, index, train)
    seed = (2411 if train else 9541) + index
    log = []
    native(a, w, seed=seed, policy=Policy(net, False), receipt_log=log, slots=3)
    states = {}
    pairs = []

    def get(prefix):
        key = tuple(tuple(actions) for _, actions, _ in prefix)
        if key not in states:
            states[key] = verify(a, w, seed, prefix)
        return key

    for n in range(len(log)):
        key = get(log[:n])
        if n >= 2:
            continue
        before = states[key]
        # Exhaustive audits run on the actual rollout states. Controlled single-action
        # branches use one representative per productive template at the same snapshot.
        representatives = {}
        for token, label in before["labels"].items():
            if label["positive"]:
                representatives.setdefault(token[0], token)
        _empty, el, _ep = replay(a, w, seed, log[:n], [])
        blank = get(el[: n + 1])
        for token in representatives.values():
            _, al, ap = replay(a, w, seed, log[:n], [token])
            after = get(al[: n + 1])
            pairs.append(
                {
                    "before": key,
                    "blank": blank,
                    "after": after,
                    "token": token,
                    "receipt": al[n][2][0],
                    "publication": ap[n + 1],
                }
            )
    data = {
        "states": states,
        "pairs": pairs,
        "autonomous": [
            tuple(tuple(actions) for _, actions, _ in log[:n]) for n in range(len(log))
        ],
        "trajectory": log,
        "seed": seed,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(data))
    tmp.replace(path)
    print(path.name, len(states), len(pairs), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for i in map(int, os.environ["TRANS_IDS"].split()):
            collect(a, i, os.environ["TRANS_SPLIT"] == "train")
