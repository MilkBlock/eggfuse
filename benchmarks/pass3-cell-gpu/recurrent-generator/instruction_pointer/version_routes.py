"""Read-only, held-context probability audit of the existing sparse mark sampler."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import torch

from boundary_inputs import BASE, CASE, frozen_tape, native
from discrete_cells import ZERO, Local, Memory, load_enc
from discrete_draft import plan, script
from discrete_study import load, views
from entry_closure import named
from recursive_train import binary, folder, read
from region_bake import linked
from region_owner import Ownership
from ripsat_layout import signatures
from scaling_bake import save
from transaction_native import execute
from version_replay import PRIOR

TARGETS = {6: [(279, True)], 8: [(544, True)], 17: [(50, False), (51, False)]}


def tree_prob(net, keys, lookup, index, mode, q):
    lo, hi = 0, len(keys)
    prob = 1.0
    while hi - lo > 1:
        mid = (hi + lo) // 2
        a, b = lookup(keys[(lo + mid - 1) // 2]), lookup(keys[(mid + hi - 1) // 2])
        right = net.choice(net.branch(q, a, b, mode)).sigmoid().item()
        if index >= mid:
            prob *= right
            lo = mid
        else:
            prob *= 1 - right
            hi = mid
    return prob


def conditional_refs(net, m, key, ctx, refs, hint, prefix):
    q = (ctx + m.graph(key)).tanh()
    probs = []
    for i, (owner, op, ver) in enumerate(refs):
        tab = m.roles[key[0]][i]
        a = owner, op
        if a not in m.pub.live or m.pub.live[a][0]["version"] != ver:
            return 0.0, probs
        slot = m.enc.nodes[m.enc.cat.inputs["generated", key[0]][i]]
        query = (q + slot).tanh()
        prob = tree_prob(net, m.rows[tab], m.key, m.index[tab, a], 1, query)
        copy = None
        if (
            hint
            and i < len(hint.refs)
            and not isinstance(hint.refs[i], Local)
            and (tab, hint.refs[i][:2]) in m.index
        ):
            copy = hint.refs[i][:2]
        elif (tab, m.last) in m.index:
            copy = m.last
        if copy is not None:
            search = (
                net.choice(net.branch(query, m.key(copy), ZERO, 2)).sigmoid().item()
            )
            prob = search * prob + (1 - search) * (copy == a)
        loc = next(
            (
                (v.cell, pc)
                for v in prefix
                for pc, t in m.output_tables[v.cell.rule].items()
                if t == tab
            ),
            None,
        )
        if loc:
            prob *= (
                1
                - net.choice(net.branch(query, ZERO, m.local_code(*loc), 2))
                .sigmoid()
                .item()
            )
        probs.append(prob)
        q = m.enc.actor.next_read((m.key(a) + slot)[None], q[None])[0]
    import math

    return math.prod(probs), probs


def training(data, forks, program):
    fit = read(Path("run-recall/discrete-computation-flow/fit.json"))
    keys = signatures(program)
    out = {}
    for name in fit["training"]:
        sig = signatures(
            read(folder(data, name.removesuffix("-roll")) / "program.json")
        )
        counts = Counter()
        with (forks / (name + ".jsonl")).open() as f:
            for row in map(json.loads, f):
                for _, src, dst in views(row):
                    for _, _, _, cell in script(plan(src), plan(dst)):
                        if cell is not None:
                            counts[sig[cell.rule]] += 1
        out[name] = {
            r: dict(rule_present=keys[r] in sig, marked_targets=counts[keys[r]])
            for r in (50, 51, 279, 544)
        }
    return out


@torch.no_grad()
def study(data, forks, actor, out):
    d = folder(data, CASE)
    prog = read(d / "program.json")
    enc, scorer = load_enc(prog, actor)
    ct = native(binary(data), "receipt-contract", d / "program.json")
    menu = linked(prog, read(BASE / "menu.json"))
    m = Memory(enc, ct, menu, scorer)
    marks, nets = load(
        SimpleNamespace(out=Path("run-recall/discrete-computation-flow"))
    )
    exact = read(PRIOR / "exact.json")
    draws = []
    submitted = []

    class Audit(Ownership):
        def run_snapshot(self, frame, *args):
            self.current = frame["run"]
            return super().run_snapshot(frame, *args)

        def send(self, items, txn, stats):
            replies = super().send(items, txn, stats)
            if len(items) <= txn.capacity:
                for item, row in zip(items, replies, strict=True):
                    c = item.cell
                    if (c.rule, c.higher) in TARGETS.get(self.current, []):
                        submitted.append(
                            dict(
                                run=self.current,
                                rule=c.rule,
                                higher=c.higher,
                                refs=c.refs,
                                status=int(row[1]),
                            )
                        )
            return replies

    policy = Audit(m, marks, nets, "empty", 4, 536, 32)
    orig = marks.draw

    def draw(m, rng, stats, hint=None, *, prefix=()):
        if policy.current in TARGETS:
            ctx = m.context() if not hint else (m.context() + m.embed(hint)).tanh()
            for k in TARGETS[policy.current]:
                p = tree_prob(marks, m.ids, m.graph, m.ids_index[k], 0, ctx)
                refs = [
                    [named(x) for x in q["parents"]]
                    for q in exact[str(policy.current)]
                    if q["rule"] == k[0]
                ]
                cond = [
                    conditional_refs(marks, m, k, ctx, r, hint, prefix) for r in refs
                ]
                draws.append(
                    dict(
                        run=policy.current,
                        rule=k[0],
                        higher=k[1],
                        p_template=p,
                        p_named_given_template=sum(v for v, _ in cond),
                        slots=[slots for _, slots in cond],
                        physical_bucket_sizes=[len(m.rows[t]) for t in m.roles[k[0]]],
                        options=len(m.ids),
                        hint=bool(hint),
                        prefix=len(prefix),
                    )
                )
        return orig(m, rng, stats, hint=hint, prefix=prefix)

    marks.draw = draw
    with TemporaryDirectory() as tmp:
        measured = execute(data, CASE, study=policy, series=tmp, seconds=240)
        issued = read(Path(tmp) / (CASE + "-stream-multi") / "issued.json")
        if (
            issued != frozen_tape()["tape"]
            or measured["state_sha"] != read(PRIOR / "generator.json")["state_sha"]
        ):
            raise ValueError("audit changed the frozen rollout")
        trials = {}
        for r in (50, 51):
            trials[r] = []
            for q in exact["17"]:
                if q["rule"] != r:
                    continue
                token = 1 << 50
                sent = dict(q, token=token)
                prefix = [v for v in issued["requests"] if v["run"] < 17]
                path = Path(tmp) / "credit.json"
                save(path, dict(issued, requests=prefix + [sent]))
                report = native(
                    binary(data),
                    "replay",
                    d / "program.json",
                    path,
                    "audit",
                    "17",
                    "--ept-origins",
                )
                origins = dict(report["ept"]["origins"])
                if (
                    report["counts"]["accepted"] != len(prefix) + 1
                    or token not in origins
                ):
                    raise ValueError("legal primitive rejected")
                trials[r].append(
                    dict(
                        request=q,
                        effective=origins[token],
                        state_sha=report["state_sha"],
                    )
                )
    save(
        out / "neural.json",
        dict(
            draws=draws,
            submitted=submitted,
            training=training(data, forks, prog),
            primitive_trials=trials,
            paid=measured["paid"],
            state_sha=measured["state_sha"],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for n in ("data", "forks", "actor", "out"):
        p.add_argument(n, type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    study(**vars(args))
