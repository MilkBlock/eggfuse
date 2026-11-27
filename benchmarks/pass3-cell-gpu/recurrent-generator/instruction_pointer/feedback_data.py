"""Native receipt-only counterfactuals and post-publication sibling branches."""

import pickle

import torch

from cell_kv_runtime import native
from competition_corpus import rowskey
from feedback_stall import folder
from partner_index_worlds import args
from state_transition_corpus import folder as previous
from state_transition_corpus import replay, verify, world
from state_transition_train import load


def public(s):
    return {k: v for k, v in s.items() if k != "request_receipts"}


class Script:
    def __init__(self, actions):
        self.actions = iter(actions)

    def prepare(self, w):
        pass

    def generate(self, w, state, rng, slots):
        return next(self.actions, ())


def traced(a, w, seed, actions, second=None):
    log = []
    pubs = []
    result = native(
        a,
        w,
        seed=seed,
        policy=Script(actions),
        receipt_memory=True,
        receipt_log=log,
        publication_log=pubs,
        diagnostic_followup=second,
    )
    return result, log


def build(a, i, train):
    name = f"{'train' if train else 'test'}-{i}.pkl"
    raw = pickle.loads((previous(a) / name).read_bytes())
    net = load(a, "transition", 71)
    w = world(a, net.actor, i, train)
    seed = raw["seed"]
    trans = []
    for key, row in raw["states"].items():
        valid = {t: l["gain"] for t, l in row["labels"].items() if l["positive"]}
        if not valid:
            continue
        _, log = traced(a, w, seed, key)
        s = log[len(key)][0]
        assert public(s) == row["state"]
        trans.append((s, valid))
    s, orig = trans[0]
    assert orig and not s["request_receipts"] and s["run"] == 1
    mids = []
    siblings = []
    good = list(orig)
    tid, refs = next(t for t in good if t[0] == w.outnames["Ready"])
    owner, op, version = refs[0]
    bad = (tid, ((owner, op, version + 1),))
    for first in [*good, bad]:
        base, log = traced(a, w, seed, [[first]])
        verified = {}
        statuses = {}
        for t in good:
            res, probe = traced(a, w, seed, [[first]], (s, [t]))
            ss = probe[1][0]
            assert public(ss) == public(s) and len(ss["request_receipts"]) == 1
            assert ss["request_receipts"][0][4] == tuple(log[0][2][0])
            gained = rowskey(res) - rowskey(base)
            statuses[t] = probe[1][2][0]
            if probe[1][2][0][1] == 0 and rowskey(base) < rowskey(res):
                verified[t] = tuple(sorted(gained))
        mids.append((ss, verified, first, statuses))
        if first in good and first[0] == tid:
            _, old, _ = replay(a, w, seed, [], [first])
            row = verify(a, w, seed, old[:1])
            assert public(log[1][0]) == row["state"]
            siblings.append(
                (
                    log[1][0],
                    {t: l["gain"] for t, l in row["labels"].items() if l["positive"]},
                )
            )
    assert len(siblings) == 2
    (folder(a) / name).write_bytes(
        pickle.dumps({"trans": trans, "mids": mids, "siblings": siblings, "orig": orig})
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for train, n in ((True, 12), (False, 6)):
            for i in range(n):
                build(a, i, train)
