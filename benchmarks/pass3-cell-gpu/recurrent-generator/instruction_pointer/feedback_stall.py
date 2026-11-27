"""Offline prefix interventions on actual EggCC trajectories, including rejected requests."""

import math
import os
from collections import Counter

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from cell_transaction import STATUS
from competition_corpus import candidates
from competition_draw import Policy
from competition_egg import egg
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import Replay
from state_transition_train import load


def folder(a):
    p = a.out / "response-memory"
    p.mkdir(exist_ok=True)
    return p


class WindowLog(list):
    def __init__(self, run):
        super().__init__()
        self.run = run

    def append(self, row):
        if row[0]["run"] == self.run:
            super().append(row)


def run(a, case):
    net = load(a, "transition", 71)
    d, align = egg(a, case)
    w = World(d, net.actor, entry_table=None, sides="")
    log = []
    result = native(
        a, w, seed=193, policy=Policy(net), receipt_log=log, reference=align
    )

    def branch(i, actions):
        return native(
            a,
            w,
            seed=193,
            policy=Replay(log[:i], actions),
            reference=align,
            slots=max(6, len(actions)),
        )

    base = branch(0, [])
    path = []
    changed = []
    flat = None
    started = False
    for j, (s, actions, qs) in enumerate(log):
        before = base
        if any(q[1] == 0 for q in qs):
            base = branch(j + 1, []) if j + 1 < len(log) else result
        change = len(set(base["facts"]) - set(before["facts"]))
        path.append(
            {
                "run": s["run"],
                "epoch": s["epoch"],
                "covered": base["covered"],
                "ops": base["ops"],
                "gain": change,
                "menu": len(s["menu"]),
                "signed": len(qs),
                "accepted": sum(q[1] == 0 for q in qs),
            }
        )
        if started and not change and flat is None:
            flat = j
        if change:
            started = True
            changed.append(j)
    assert base["facts"] == result["facts"]
    # Re-test named requests from the productive window if the Recipe still schedules them.
    audits = []
    selected = sorted(
        {
            flat - 1,
            flat,
            min(flat + 1, len(log) - 1),
            min(changed[-1] + 1, len(log) - 1),
        }
    )
    for j in selected:
        s, actions, qs = log[j]
        before = branch(j, [])
        banks = Counter(p[3] for p in s["ports"])
        domains = {t: math.prod(banks[tab] for tab in w.roles[t]) for t in s["menu"]}
        public_refs = {p[0] for p in s["ports"]}
        prior = (
            [
                t
                for t in log[j - 1][1]
                if t[0] in domains and all(r in public_refs for r in t[1])
            ]
            if j
            else []
        )

        # Take turns between template domains; expensive high-arity domains stay censored.
        streams = [candidates(w, dict(s, menu=[t])) for t in domains if domains[t]]
        choices = list(dict.fromkeys(actions + prior))
        while streams and len(choices) < 16:
            keep = []
            for it in streams:
                item = next(it, None)
                if item is not None:
                    keep.append(it)
                    if item not in choices:
                        choices.append(item)
                    if len(choices) >= 16:
                        break
            streams = keep
        net.prepare(w)
        m = net.state(w, s) if choices else None
        findings = []
        for tok in choices:
            # Verify prefix and immediate receipt as well as exported facts.
            rows = WindowLog(s["run"])
            z = native(
                a,
                w,
                seed=193,
                policy=Replay(log[:j], [tok]),
                receipt_log=rows,
                reference=align,
            )
            assert rows[0][0] == s
            new = sorted(set(z["facts"]) - set(before["facts"]))
            findings.append(
                {
                    "token": tok,
                    "reason": STATUS[rows[0][2][0][1]],
                    "p": float((-net.token_loss(w, m, tok)).exp()),
                    "gained": new,
                    "lost": sorted(set(before["facts"]) - set(z["facts"])),
                }
            )
        audits.append(
            {
                "index": j,
                "run": s["run"],
                "domains": domains,
                "menu": s["menu"],
                "typed_ports": banks,
                "actions": actions,
                "status": [STATUS[q[1]] for q in qs],
                "repeat": len(actions) - len(set(actions)),
                "exhaustive": len(findings) == sum(domains.values()),
                "probes": findings,
            }
        )
    store(
        folder(a) / f"stall-{case}.json",
        {
            "case": case,
            "seed": 193,
            "weight": 71,
            "first": flat,
            "last_gain": changed[-1],
            "path": path,
            "audits": audits,
        },
    )
    print(
        case, "stall", flat, "last gain", changed[-1], "windows", len(log), flush=True
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        for case in os.getenv("FB_CASES", "fact loopfact sum-divisors").split():
            run(args(), case)
