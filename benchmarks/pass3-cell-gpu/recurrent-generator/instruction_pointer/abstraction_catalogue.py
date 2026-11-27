"""Compare catalogue depth on identical native programs, fixed entry and frozen architecture."""

import json
import pickle
import random
from time import perf_counter

import torch

from cell_kv_runtime import native
from cell_kv_world import World, make
from competition_corpus import candidates, rowskey
from constructible_study import TracePolicy, directory
from feedback_train import get
from partner_index_worlds import args

CATALOGUES = ("primitive", "short", "medium", "multi")
STEPS = (0, 32, 96, 192)


def build_world(a, actor, i, train, catalogue):
    depth = (4, 6)[i % 2] if train else (5, 7)[i % 2]
    seed = (800031 if train else 991511) + i
    root = make(
        a,
        f"abstraction-constructible-{seed}",
        depth,
        2,
        seed,
        fork=i % 3 == 0,
        common=True,
    )
    w = World(root, actor)
    bodies = w.layouts[w.primitives :]
    w.layouts = w.layouts[: w.primitives]
    w.export_pc = {}
    for size in (2, depth + 2):
        if catalogue not in (("short", "multi") if size == 2 else ("medium", "multi")):
            continue
        for full in bodies:
            body = full[:size]
            rid = body[-1][0]
            # The controlled suffix has exactly one public relation output.
            (pc,) = w.outputs[rid].values()
            w.export_pc[len(w.layouts)] = pc
            w.layouts.append(body)
    return w


def corpus(a, w, path):
    if path.exists():
        return pickle.loads(path.read_bytes())
    samples = []

    def finish(state, tokens):
        return native(
            a, w, teacher="primitive", branch=(state, tokens), receipt_memory=True
        )

    for s, _ in native(a, w, teacher="primitive", receipt_memory=True):
        baseline = rowskey(finish(s, []))
        valid = []
        for tok in candidates(w, s):
            z = finish(s, [tok])
            rows = rowskey(z)
            if baseline < rows and (
                tok[0] < w.primitives or z["stats"]["branch_higher_completed"]
            ):
                valid.append(tok)
        if valid:
            samples.append((s, valid))
    if not samples:
        raise ValueError("native audit found no positive training token")
    path.write_bytes(pickle.dumps(samples))
    return samples


def score(net, data):
    total = 0
    n = 0
    with torch.no_grad():
        for w, states in data:
            net.prepare(w)
            for s, ts in states:
                m = net.state(w, s)
                total += sum(float(net.token_loss(w, m, t)) for t in ts) / len(ts)
                n += 1
    return total / n


def study(a, root, cat, seed, train, test):
    net = get(a, "visible", seed)
    net.condition_on_types = True
    rng = random.Random(seed)
    opt = torch.optim.AdamW(
        [p for p in net.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    elapsed = 0.0
    rows = []
    for step in range(STEPS[-1] + 1):
        if step in STEPS:
            net.eval()
            held_ce = score(net, test)
            print(cat, seed, step, held_ce, flush=True)
            with torch.no_grad():
                for i, (w, _) in enumerate(test):
                    for draw in (193, 827):
                        net.static_cache.clear()
                        pol = TracePolicy(net, True)
                        z = native(
                            a,
                            w,
                            policy=pol,
                            receipt_memory=True,
                            slots=6,
                            submit_pages=2,
                            seed=draw,
                            receipt_log=pol,
                        )
                        rows.append(
                            dict(
                                cat=cat,
                                seed=seed,
                                step=step,
                                exposures=step * 16,
                                train_s=elapsed,
                                index=i,
                                draw=draw,
                                ce=held_ce,
                                lengths=[len(b) for b in w.layouts[w.primitives :]],
                                decisions=pol.count["signed"],
                                requested_slots=pol.count["offered"],
                                calls=pol.count["distribution_reads"],
                                read_s=pol.decode_s,
                                fit_states=sum(len(s) for _, s in train),
                                reason=z["receipts"],
                                **z,
                            )
                        )
            (root / f"scale-{cat}-{seed}.json").write_text(
                json.dumps(rows, separators=(",", ":"))
            )
        if step == STEPS[-1]:
            break
        start = perf_counter()
        net.train()
        losses = []
        for _ in range(4):
            w, batch = rng.choice(train)
            s, ts = rng.choice(batch)
            net.prepare(w)
            m = net.state(w, s)
            picks = rng.choices(ts, k=4)
            terms = {t: net.token_loss(w, m, t) for t in set(picks)}
            losses.extend(terms[t] for t in picks)
        opt.zero_grad(set_to_none=True)
        loss = torch.stack(losses).mean()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
        opt.step()
        elapsed += perf_counter() - start
    torch.save(net.state_dict(), root / f"scale-{cat}-{seed}.pt")


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    root = directory(a)
    actor = get(a, "visible", 71).actor
    for cat in CATALOGUES:
        datasets = []
        for train, n in ((True, 8), (False, 4)):
            data = []
            for i in range(n):
                w = build_world(a, actor, i, train, cat)
                data.append(
                    (w, corpus(a, w, root / f"scale-{cat}-{int(train)}-{i}.pkl"))
                )
            datasets.append(data)
        for seed in (71, 113):
            study(a, root, cat, seed, *datasets)
