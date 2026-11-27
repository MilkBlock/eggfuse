"""Two submitted transactions before Seal, and a mutable-port version probe."""

import pickle

import torch

from cell_kv_runtime import logical_rows, native
from cell_kv_world import World, compile_world
from cell_transaction import STATUS
from competition_corpus import rowskey
from competition_egg import network
from completion_context import read
from partner_index_worlds import args
from state_transition_corpus import Replay, folder, replay, verify, world


def within(a, w, raw):
    seed = raw["seed"]
    before = raw["states"][()]
    producer = w.outnames["Ready"]
    first = next(
        t for t, l in before["labels"].items() if t[0] == producer and l["positive"]
    )
    base, _, _ = replay(a, w, seed, [], [first])
    out = {}
    for token in before["labels"]:
        log = []
        pub = []
        res = native(
            a,
            w,
            seed=seed,
            policy=Replay([], [first]),
            receipt_log=log,
            publication_log=pub,
            diagnostic_followup=(before["state"], [token]),
        )
        assert log[0][0] == log[1][0] and len(log[0][2]) == len(log[1][2]) == 1
        out[token] = {
            "gain": tuple(sorted(rowskey(res) - rowskey(base))),
            "lost": tuple(sorted(rowskey(base) - rowskey(res))),
            "receipt": log[1][2][0],
            "first_receipt": log[0][2][0],
        }
    assert STATUS[out[first]["receipt"][1]] == "duplicate" and not out[first]["gain"]
    assert any(t != first and v["gain"] for t, v in out.items())
    return {"first": first, "labels": out, "post_submit": log[1][0]}


def versions(a, actor):
    src = """(relation Seed (i64))
(function Best (i64) i64 :merge (max old new))
(relation Observed (i64))
(Seed 3)
(set (Best 3) 10)
(ruleset update)
(rule ((Seed x)) ((set (Best x) 20)) :ruleset update)
(rule ((= v (Best x))) ((Observed v)) :ruleset update)
(run-schedule (run update) (run update) (run update))
"""
    w = World(
        compile_world(a, "transition-version-1", src), actor, entry_table=None, sides=""
    )
    seed = 7161
    expected = {
        t for t in logical_rows(read(w.dir / "reference.json")) if t[0] == "Observed"
    }

    def reference(graph):
        return {t for t in logical_rows(graph) if t[0] == "Observed"}, expected

    initial = verify(a, w, seed, [], reference)
    producer = next(t for t in initial["labels"] if "Best" in w.outputs[t[0]])
    _r, log, pubs = replay(a, w, seed, [], [producer], reference)
    after = verify(a, w, seed, log[:1], reference)
    blank = verify(a, w, seed, replay(a, w, seed, [], [], reference)[1][:1], reference)
    stale = {}
    for t in initial["labels"].keys() - after["labels"].keys():
        _res, actions, _ = replay(a, w, seed, log[:1], [t], reference)
        stale[t] = actions[1][2][0]
    assert stale and all(STATUS[q[1]] == "version" for q in stale.values())
    return {
        "initial": initial,
        "after": after,
        "blank": blank,
        "producer": producer,
        "stale": stale,
        "pubs": pubs,
        "dir": w.dir,
    }


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    net = network(a, "B", 71)
    with torch.no_grad():
        v = versions(a, net.actor)
        (folder(a) / "versions.pkl").write_bytes(pickle.dumps(v))
        for i in range(6):
            r = pickle.loads((folder(a) / f"test-{i}.pkl").read_bytes())
            p = within(a, world(a, net.actor, i, False), r)
            (folder(a) / f"within-{i}.pkl").write_bytes(pickle.dumps(p))
            w = world(a, net.actor, i, False)
            siblings = []
            for t, v in r["states"][()]["labels"].items():
                if t[0] != w.outnames["Ready"] or not v["positive"]:
                    continue
                _, log, _ = replay(a, w, r["seed"], [], [t])
                siblings.append((t, verify(a, w, r["seed"], log[:1])))
            assert len(siblings) == 2
            (folder(a) / f"siblings-{i}.pkl").write_bytes(pickle.dumps(siblings))
