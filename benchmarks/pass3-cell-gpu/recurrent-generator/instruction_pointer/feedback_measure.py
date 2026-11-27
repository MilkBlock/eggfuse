"""Paired likelihood of full named tokens at identical public memories."""

import os
import pickle
from itertools import product
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_transaction import STATUS
from competition_corpus import audit
from competition_corpus import world as basic_world
from competition_results import table
from feedback_data import public
from feedback_stall import folder
from feedback_train import get
from partner_index_worlds import args
from state_transition_corpus import world


def prob(net, w, s, domain):
    m = net.state(w, s)
    assert m["refs"] == [p[0] for p in s["ports"]]
    return {t: float((-net.token_loss(w, m, t)).exp()) for t in domain}


def run(a, d):
    reports = []
    siblings = []
    failed = []
    for arm, seed in product(("old", "blind", "visible", "muted"), (71, 113)):
        net = get(a, "visible" if arm == "muted" else arm, seed)
        for i in range(6):
            w = world(a, net.actor, i, False)
            net.prepare(w)
            data = pickle.loads((folder(a) / f"test-{i}.pkl").read_bytes())
            domain = data["orig"]
            first_state = public(data["mids"][0][0])
            before = prob(net, w, first_state, domain)
            pp = {}
            samples = {}
            for s, v, t, q in data["mids"]:
                assert public(s) == first_state
                pp[t] = prob(net, w, s if arm == "visible" else public(s), domain)
                samples[t] = (s, v, q)
            for t in domain:
                s, v, answers = samples[t]
                p = pp[t]
                assert (
                    t not in v
                    and STATUS[answers[t][1]] == "duplicate"
                    and set(v) == domain.keys() - {t}
                )
                alts = [
                    q for action, q in pp.items() if action in domain and action != t
                ]
                same = [
                    q
                    for action, q in pp.items()
                    if action in domain and action != t and action[0] == t[0]
                ]
                reports.append(
                    {
                        "arm": arm,
                        "seed": seed,
                        "case": i,
                        "tid": t[0],
                        "refs": repr(t[1]),
                        "before": before[t],
                        "after": p[t],
                        "other_receipt": sum(q[t] for q in alts) / len(alts),
                        "same_template_other_ref": sum(q[t] for q in same) / len(same)
                        if same
                        else "",
                        "remaining_before": sum(before[x] for x in v),
                        "remaining_after": sum(p[x] for x in v),
                    }
                )
            (bad,) = pp.keys() - domain.keys()
            st, valid, _ = samples[bad]
            same_owner = next(
                t for t in domain if t[0] == bad[0] and t[1][0][:2] == bad[1][0][:2]
            )
            failed.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "case": i,
                    "status": STATUS[st["request_receipts"][0][4][1]],
                    "valid": len(valid),
                    "after_failed": pp[bad][same_owner],
                    "after_accepted": pp[same_owner][same_owner],
                    "before": before[same_owner],
                }
            )
            pair = []
            for s, v in data["siblings"]:
                (good,) = [t for t in v if t[0] >= w.primitives]
                domain2 = [(k, good[1]) for k in range(w.primitives, len(w.layouts))]
                # Here the sum of named Higher probabilities is the whole Higher family.
                for tid, refs in domain2:
                    (expected,) = w.roles[w.layouts[tid][0][0]]
                    assert tuple(p[0] for p in s["ports"] if p[3] == expected) == refs
                p = prob(net, w, s if arm == "visible" else public(s), domain2)
                pair.append((good, p))
            assert pair[0][0][0] != pair[1][0][0] and pair[0][0][1] == pair[1][0][1]
            both = all(p[g] > max(v for t, v in p.items() if t != g) for g, p in pair)
            for good, p in pair:
                siblings.append(
                    {
                        "arm": arm,
                        "seed": seed,
                        "case": i,
                        "tid": good[0],
                        "higher": sum(p.values()),
                        "conditional": p[good] / sum(p.values()),
                        "full": p[good],
                        "both": both,
                    }
                )
    basic = []
    probe = get(a, "old", 71)
    for i in range(8):
        w = basic_world(a, probe.actor, "single", i, False)
        windows = native(a, w, teacher="higher")
        s = windows[0][0]
        verified, _ = audit(a, w, s)
        good = {t for t in verified if t[0] >= w.primitives}
        assert good
        for arm, seed in product(("old", "blind", "visible"), (71, 113)):
            net = get(a, arm, seed)
            net.prepare(w)
            p = prob(net, w, s, verified)
            basic.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "case": i,
                    "correct_higher": sum(p[t] for t in good),
                    "all_verified": sum(p.values()),
                }
            )
    table(d, "basic", basic)
    table(d, "pre-seal", reports)
    table(d, "failed", failed)
    table(d, "higher", siblings)


if __name__ == "__main__":
    torch.set_num_threads(1)
    d = Path(os.getenv("RESULTS_DIR", "run-recall/response-memory"))
    d.mkdir(exist_ok=True, parents=True)
    with torch.no_grad():
        run(args(), d)
