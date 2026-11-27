"""Offline causal wake forks. The native scheduler observer never enters the decoder."""

import json
import os
import pickle
import random
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from cell_transaction import STATUS
from competition_corpus import rowskey
from constructible_study import TracePolicy
from feedback_data import Script
from foundation_fit import model
from foundation_world import folder
from partner_index_worlds import args


def world(a, actor, i, train, distinct=False):
    seed = (914100 if train else 978600) + i
    rng = random.Random(seed)
    branches = list("AB")
    rng.shuffle(branches)
    lines = [
        "(ruleset root)",
        "(ruleset one)",
        "(ruleset two)",
        "(relation Feed (i64))",
    ]
    for b in branches:
        result = "(+ x 7)" if distinct and b == "B" else "x"
        lines += [
            f"(relation Seed{b} (i64))",
            f"(relation Hit{b} (i64))",
            f"(rule ((Seed{b} x)) ((Hit{b} {result})) :ruleset root)",
            f"(rule ((Feed x)) ((Seed{b} (+ x 17))) :ruleset one)",
            f"(rule ((Feed x)) ((Seed{b} (+ x 39))) :ruleset two)",
        ]
    values = rng.sample(range(10000, 900000), 3)
    inputs = [f"(SeedA {values[0]})", f"(SeedB {values[1]})", f"(Feed {values[2]})"]
    rng.shuffle(inputs)
    lines += inputs + [
        "(run-schedule (run root) (run root) (run one) (run root) (run two) (run root) (run root))"
    ]
    return World(
        compile_world(
            a,
            f"wake-ce-{seed}-asym" if distinct else f"wake-ce-{seed}",
            "\n".join(lines) + "\n",
        ),
        actor,
        sides="",
        entry_table="HitA",
    )


def samples(a, w, seed):
    def replay(script):
        hist = []
        with TemporaryDirectory() as t:
            path = Path(t) / "observer"
            with patch.dict(os.environ, {"EGGFUSE_QUERY_OBSERVER": str(path)}):
                z = native(
                    a,
                    w,
                    policy=Script(script),
                    receipt_log=hist,
                    receipt_memory=True,
                    seed=seed,
                )
            frames = [json.loads(l) for l in path.read_text().splitlines()]
        live = [(r, e, flags) for r, e, on, end, flags in frames if on and not end]
        for (r, e, flags), row in zip(live, hist, strict=True):
            snap = row[0]
            if (r, e) != (snap["run"], snap["epoch"]) or [
                t for t, _, _ in flags
            ] != list(snap["menu"]):
                raise ValueError("native observer and public frame disagree")
        return (
            hist,
            {
                r: {tid: (wm, active) for tid, wm, active in flags}
                for r, e, on, end, flags in frames
                if on and not end
            },
            rowskey(z),
        )

    idle, _, _ = replay([])

    def signed(j, b):
        s = idle[j][0]
        (tid,) = [t for t in s["menu"] if "Seed" + b in w.outputs[t]]
        (ref,) = [p[0] for p in s["ports"] if p[3] == w.roles[tid][0]]
        return tid, (ref,)

    obs = []
    for first, other in (("A", "B"), ("B", "A")):
        script = [[], [], [signed(2, first)], [], [signed(4, other)], []]
        hist, flags, _ = replay(script)

        def new_token(s, b):
            tid = w.outnames["Hit" + b]
            (ref,) = [
                p[0] for p in s["ports"] if p[3] == w.roles[tid][0] and p[0][0] > 0
            ]
            return tid, (ref,)

        target = new_token(hist[3][0], first)
        for consumed in (False, True):
            script[3] = [target] if consumed else []
            hist, flags, _ = replay(script)
            led = []
            for j in (0, 1, 3, 5, 6):
                s = hist[j][0]
                baseline = replay(script[:j])[2]
                items = []
                for tid in s["menu"]:
                    for p in s["ports"]:
                        if p[3] != w.roles[tid][0]:
                            continue
                        t = (tid, (p[0],))
                        trace, _, facts = replay(script[:j] + [[t]])
                        assert trace[j][0] == s
                        status = STATUS[trace[j][2][0][1]]
                        items.append((t, status, baseline < facts))
                led.append((s, flags[s["run"]], items))
            wake, late = led[2], led[3]
            assert wake[1][target[0]][1] and not late[1][target[0]][1]
            assert (target, "accepted", True) in wake[2]
            assert (target, "untriggered_rule", False) in late[2]
            assert any(g for t, v, g in late[2])
            obs.append(
                {"first": first, "consumed": consumed, "target": target, "states": led}
            )
    return obs


def measure(net, ds):
    rows = []
    for i, (w, obs) in enumerate(ds):
        net.prepare(w)
        for o in obs:
            t = o["target"]
            for phase, (s, flags, items) in enumerate(o["states"]):
                if phase not in (2, 3):
                    continue
                m = net.state(w, s)
                probs = {
                    tok: float((-net.token_loss(w, m, tok)).exp())
                    for tok, _, _ in items
                }
                active = {tok for tok, status, g in items if g}
                roots = list(m["families"])
                rows.append(
                    {
                        "i": i,
                        "first": o["first"],
                        "consumed": o["consumed"],
                        "phase": phase,
                        "p": probs[t],
                        "template": float(m["root_lp"][roots.index(t[0])].exp()),
                        "good": sum(probs[x] for x in active),
                        "dirty": flags[t[0]][1],
                        "wm": flags[t[0]][0],
                        "run": s["run"],
                        "epoch": s["epoch"],
                        "receipts": len(s["request_receipts"]),
                    }
                )
    return rows


def audit(net, w, o):
    s, flags, _ = o["states"][3]
    token = o["target"]
    net.prepare(w)
    query = []

    def qhook(layer, inputs):
        if not query:
            query.append(inputs[0])

    handle = net.actor.query.register_forward_pre_hook(qhook)
    values = []

    def capture_values(layer, inputs, output):
        if not values:
            v = output.detach().requires_grad_()
            values.append(v)
            return v

    vh = net.actor.dynamic.register_forward_hook(capture_values)
    rec = []
    static = net.receipt_vectors

    def hook(*args):
        y = static(*args).detach().requires_grad_()
        rec.append(y)
        return y

    try:
        dirty = torch.tensor(float(flags[token[0]][1]), requires_grad=True)
        wm = torch.tensor(float(flags[token[0]][0]), requires_grad=True)
        state = dict(s, dirty=dirty, watermark=wm)
        with patch.object(net, "receipt_vectors", hook):
            m = net.state(w, state)
            lp = -net.token_loss(w, m, token)
            root = m["root_lp"][list(m["families"]).index(token[0])]
            d, r, b, c, dv = torch.autograd.grad(
                lp,
                (query[0], rec[0], dirty, wm, values[0]),
                allow_unused=True,
                retain_graph=True,
            )
            qg, rg, vg = torch.autograd.grad(
                root, (query[0], rec[0], values[0]), allow_unused=True
            )
            ids = list(m["families"])
            difference = float(
                (net.cache[1][ids[0]] - net.cache[1][ids[1]]).abs().max()
            )
            rel = float((m["root_lp"][0] - m["root_lp"][1]).detach())
    finally:
        handle.remove()
        vh.remove()
    muted = dict(s, request_receipts=())
    return {
        "run": s["run"],
        "first_query_log_state_gradient": d[:5].tolist(),
        "receipt_grad": float(r.norm()),
        "public_value_grad": float(dv.norm()),
        "template_query_grad": float(qg.norm()),
        "template_receipt_grad": float(rg.norm()),
        "template_public_grad": float(vg.norm()),
        "static_code_maxdiff": difference,
        "root_log_odds": rel,
        "dirty_unused": b is None,
        "wm_unused": c is None,
        "p": float(lp.detach().exp()),
        "muted_p": float(
            (-net.token_loss(w, net.state(w, muted), token)).detach().exp()
        ),
    }


def main(a, distinct=False):
    actor = model(a, 71, 32).actor
    tag = "wake-asym" if distinct else "wake"
    d = folder(a)
    ds = []
    for train, n in ((True, 12), (False, 6)):
        batch = []
        for i in range(n):
            w = world(a, actor, i, train, distinct)
            p = d / f"{tag}-{train}-{i}.pkl"
            if not p.exists():
                p.write_bytes(pickle.dumps(samples(a, w, 107 * i + 151)))
            batch.append((w, pickle.loads(p.read_bytes())))
        ds.append(batch)
    train, test = ds
    for seed in (71, 113):
        n = model(a, seed, 32)
        rng = random.Random(seed + 311)
        opt = torch.optim.AdamW(
            [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
        )
        out = []
        for step in range(513):
            if step in (0, 32, 128, 512):
                n.eval()
                n.physical = ("held", 0)
                with torch.no_grad():
                    rows = measure(n, test)
                    live = []
                    for w, _ in test:
                        pol = TracePolicy(n, True)
                        z = native(
                            a,
                            w,
                            seed=193,
                            slots=6,
                            submit_pages=2,
                            policy=pol,
                            receipt_log=pol,
                            receipt_memory=True,
                        )
                        live.append(z)
                grads = [audit(n, w, os_[0]) for w, os_ in test]
                out.append({"step": step, "rows": rows, "grads": grads, "live": live})
            if step == 512:
                break
            n.train()
            batch = []
            for _ in range(4):
                w, obs = rng.choice(train)
                phase = rng.choice((0, 2, 3))
                s, _, items = rng.choice(obs)["states"][phase]
                picks = rng.choices([t for t, _, g in items if g], k=4)
                n.prepare(w)
                m = n.state(w, s)
                losses = {t: n.token_loss(w, m, t) for t in set(picks)}
                batch.extend(losses[t] for t in picks)
            opt.zero_grad(set_to_none=True)
            torch.stack(batch).mean().backward()
            torch.nn.utils.clip_grad_norm_(n.parameters(), 3)
            opt.step()
        (d / f"{tag}-fit-{seed}.json").write_text(json.dumps(out))
        torch.save(n.state_dict(), d / f"{tag}-fit-{seed}.pt")


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    main(a)
    main(a, True)
