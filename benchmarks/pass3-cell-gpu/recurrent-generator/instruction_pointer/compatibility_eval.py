"""Offline paired attention interventions and separate native, unprompted evaluation."""

import json
import math
import os
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World, compile_world
from compatibility_study import ARMS, SEEDS, align, checkpoint, policy
from compatibility_world import cases, source, world
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding_study import save


def readout(net, m, ctx, owner, hint=False, share=()):
    """Recompute the exact C readout, optionally crossing ctx or forcing one owner."""
    ids = m["menu"]
    codes = net.cache[1][ids]
    q = net.actor.query(ctx + codes)
    if share:
        q = q.clone()
        q[share] = q[share].mean(0)
    scale = math.sqrt(q.shape[-1])
    qk = q @ m["keys"].T / scale
    pl = q @ m["ek"].T / scale
    pv = net.actor.latent(m["ext"])
    msg = torch.stack([pl[:, ix].softmax(1) @ pv[ix] for ix in m["siblings"]], 1)
    weights = (qk + (q[:, None] * msg).sum(-1) / scale).softmax(1)
    val = m["vals"][None] + msg
    read = val[:, owner] if hint else (weights[:, :, None] * val).sum(1)
    logits = (net.actor.query(ctx + read) * net.actor.input_role(codes)).sum(-1) / scale
    return logits.log_softmax(0), qk[:, owner], weights[:, owner]


def diagnose(net, ws, entries, ref, tids):
    mem = []
    for w, (s, _) in zip(ws, entries, strict=True):
        net.prepare(w)
        mem.append(net.state(w, s))
    assert (
        ws[0].prog["recipe"] == ws[1].prog["recipe"] and ws[0].layouts == ws[1].layouts
    )
    net.prepare(ws[0])
    c0 = net.cache[1].clone()
    net.prepare(ws[1])
    torch.testing.assert_close(c0, net.cache[1], rtol=0, atol=0)
    out = []
    for flip, (w, m) in enumerate(zip(ws, mem, strict=True)):
        idx = m["pos"][ref]
        g = int(m["group"][idx])
        entries_i = [m["menu"].index(t) for t in tids]
        lp, qk, att = readout(net, m, m["ctx"], g)
        torch.testing.assert_close(lp, m["lp"], rtol=1e-5, atol=2e-5)

        def diff(v, indices=entries_i):
            return float(v[indices[0]] - v[indices[1]])

        # Hold the global pooled summary or local KV fixed on the first pair member.
        local = readout(net, m, mem[0]["ctx"], g)[0]
        global_only = readout(
            net, mem[0], m["ctx"], int(mem[0]["group"][mem[0]["pos"][ref]])
        )[0]
        hint = readout(net, m, m["ctx"], g, hint=True)[0]
        shared = readout(net, m, m["ctx"], g, share=entries_i)[0]
        bind = torch.stack([net.address(w, m, t, [])[idx] for t in tids])
        pairlp = lp[entries_i]
        complete = pairlp + bind
        out.append(
            {
                "flip": flip,
                "ref": ref,
                "gold": tids[flip],
                "ids": tids,
                "template": pairlp.exp().tolist(),
                "qk": qk[entries_i].tolist(),
                "attention": att[entries_i].tolist(),
                "complete": complete.exp().tolist(),
                "bind": bind.exp().tolist(),
                "p_gold_vs_other": float(pairlp.softmax(0)[flip]),
                "margin": diff(lp),
                "qk_margin": diff(qk),
                "full_margin": float(complete[0] - complete[1]),
                "local_margin": diff(local),
                "global_margin": diff(global_only),
                "hint_margin": diff(hint),
                "shared_margin": diff(shared),
                "input_key_change": float(
                    (
                        m["keys"][g]
                        - mem[0]["keys"][int(mem[0]["group"][mem[0]["pos"][ref]])]
                    ).norm()
                ),
                "structure_distance": float((c0[tids[0]] - c0[tids[1]]).norm()),
            }
        )
    return out


class ObservePage:
    def __init__(self, net):
        self.net = net
        self.page = None

    def prepare(self, w):
        self.net.prepare(w)

    def generate(self, w, s, rng, slots):
        choices = self.net.generate(w, s, rng, slots)
        if self.page is None:
            self.page = s, choices
        return choices


def trace_hits(pages, entries, w):
    # Only after native execution. Match actual randomized addresses to public
    # rows for offline scoring, never hand the correct row to the policy.
    result = []
    left, right = pages[0][0], pages[1][0]
    l = {p[0]: p for p in left["ports"]}
    r = {p[0]: p for p in right["ports"]}
    assert l.keys() == r.keys()
    (changed,) = [ref for ref in l if l[ref] != r[ref]]
    for flip, ((s, decisions), (ts, targets)) in enumerate(
        zip(pages, entries, strict=True)
    ):
        gold_tid = w.primitives + flip
        truth = {(tuple(p[4]), p[3]): p[0] for p in ts["ports"]}
        assert len(truth) == len(ts["ports"])
        refmap = {p[0]: truth[(tuple(p[4]), p[3])] for p in s["ports"]}
        correct = (gold_tid, (changed,))
        assert (gold_tid, (refmap[changed],)) in targets
        result.append(
            {
                "flip": flip,
                "slots": len(decisions),
                "correct": sum(x == correct for x in decisions),
                "any_valid": sum(
                    (t, tuple(refmap[r] for r in refs)) in targets
                    for t, refs in decisions
                ),
                "tokens": decisions,
                "changed": changed,
            }
        )
    return result


@torch.no_grad()
def evaluate(a):
    actor = load_actor(a.actor, True)
    policies = {}
    for arm in ARMS:
        for seed in SEEDS if arm != "A" else SEEDS[:1]:
            net = policy(a, arm).eval()
            net.load_state_dict(torch.load(checkpoint(a, arm, seed), weights_only=True))
            policies[arm, seed] = net
    fit_rec = set()
    fit_sig = set()
    for n, sp in cases("fit"):
        w = world(a, actor, n, sp, False)
        fit_rec.add(w.prog["recipe"]["sha256"])
        fit_sig.update(digest(w))
    known = set(fit_sig)
    prior_training = Path(os.environ["ARTIFACT_ROOT"]) / "token-embedding/worlds"
    for folder in prior_training.glob("fit-*"):
        known.update(digest(World(folder, actor)))
    hist = json.loads(Path("run-recall/cell-kv/manifest.json").read_text())
    known.update(
        x for p in hist["programs"] if p["split"] == "train" for x in p["signatures"]
    )
    native_rows = []
    probes = []
    controls = []
    manifest = []
    address = []
    for name, sp in cases("test"):
        ws = [world(a, actor, name, sp, f) for f in (False, True)]
        entries = [native(a, w, teacher="higher")[0] for w in ws]
        ref, tids = align(*entries, ws[0])
        sig = digest(ws[0])
        seen = name.startswith("seen")
        assert (ws[0].prog["recipe"]["sha256"] in fit_rec) == seen
        assert all(h in fit_sig for h in sig) if seen else not set(sig) & known
        manifest.append(
            {
                "case": name,
                "recipe": ws[0].prog["recipe"]["sha256"],
                "higher": sig,
                "options": entries[0][0]["menu"],
                "ref": ref,
                "seed_hashes": [
                    next(p[4] for p in e[0]["ports"] if p[0] == ref) for e in entries
                ],
                "interfaces": [
                    (w.roles[b[0][0]], w.outputs[b[0][0]], w.outputs[b[-1][0]])
                    for w in ws[:1]
                    for b in w.layouts[w.primitives :]
                ],
            }
        )
        assert len(set(map(str, manifest[-1]["interfaces"]))) == 1
        for (arm, seed), net in policies.items():
            for row in diagnose(net, ws, entries, ref, tids):
                probes.append(dict(case=name, arm=arm, seed=seed, **row))
        for draw in (193, 827):
            for block in (0, 1):
                order = list(policies)
                if (block + (draw == 827)) % 2:
                    order.reverse()
                for arm, seed in order:
                    net = policies[arm, seed]
                    pages = []
                    results = []
                    for w in ws:
                        spy = ObservePage(net)
                        # Charge cold graph encoding equally on every measured run.
                        net.static_cache.clear()
                        result = native(a, w, policy=spy, seed=draw)
                        pages.append(spy.page)
                        results.append(result)
                    scores = trace_hits(pages, entries, ws[0])
                    if block == 0:
                        ar = diagnose(net, ws, pages, scores[0]["changed"], tids)
                        canonical = [
                            r
                            for r in probes
                            if (r["case"], r["arm"], r["seed"]) == (name, arm, seed)
                        ]
                        for row, orig in zip(ar, canonical, strict=True):
                            address.append(
                                {
                                    "case": name,
                                    "arm": arm,
                                    "seed": seed,
                                    "draw": draw,
                                    "flip": row["flip"],
                                    "source": ref,
                                    "physical": scores[0]["changed"],
                                    "delta": max(
                                        abs(x - y)
                                        for x, y in zip(
                                            row["complete"], orig["complete"]
                                        )
                                    ),
                                }
                            )
                    for p, res in zip(scores, results, strict=True):
                        native_rows.append(
                            dict(
                                case=name,
                                arm=arm,
                                seed=seed,
                                draw=draw,
                                block=block,
                                **p,
                                **res,
                            )
                        )
        if name in ("seen-0", "new-6"):
            # Separate the effect of guard vs arithmetic while preserving interface.
            depth, sides, jobs, dist, rs, inst, fork = sp
            for kind in ("guard", "op"):
                vs = [
                    World(
                        compile_world(
                            a,
                            f"{name}-{kind}-{f}",
                            source(
                                depth,
                                sides,
                                jobs,
                                dist,
                                rs,
                                inst,
                                f,
                                fork,
                                invert_guard=kind == "guard",
                                invert_op=kind == "op",
                            ),
                        ),
                        actor,
                        sides,
                    )
                    for f in (0, 1)
                ]
                checked = [native(a, w, teacher="higher")[0] for w in vs]
                for f, (s, targets) in enumerate(checked):
                    assert s == entries[f][0]
                    expected = tids[1 - f if kind == "guard" else f]
                    assert (expected, (ref,)) in targets
                for (arm, seed), net in policies.items():
                    net.prepare(ws[0])
                    orig = net.cache[1][tids].clone()
                    for r in diagnose(net, vs, checked, ref, tids):
                        f = r["flip"]
                        controls.append(
                            {
                                "case": name,
                                "kind": kind,
                                "arm": arm,
                                "seed": seed,
                                "flip": f,
                                "code_shift": (net.cache[1][tids] - orig)
                                .norm(dim=1)
                                .tolist(),
                                "margin": r["margin"],
                                "expected_left": (f == 0) != (kind == "guard"),
                            }
                        )
        for f, data in [
            ("native", native_rows),
            ("probes", probes),
            ("controls", controls),
            ("pairs", manifest),
            ("address", address),
        ]:
            save(a.out / f"{f}.json", data)
        print("evaluated", name, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    evaluate(args())
