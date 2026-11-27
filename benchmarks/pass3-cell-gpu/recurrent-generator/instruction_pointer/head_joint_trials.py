"""Frozen shuffled-address tests, paired native execution, and synchronized Metal costs."""

from copy import copy
from statistics import median
from time import perf_counter

import numpy as np
import torch

import head_joint_index as joint
import partner_index as old
from binding_model import read_packet
from binding_online import trial
from completion_context import native
from credit_scale_buffer import submit
from discrete_draft import Cell
from first_parent import records
from head_joint_worlds import suite
from partner_index_trials import policy
from partner_index_worlds import args, frozen
from selective_replication import AllocationTrace
from selective_trials import inputs


def clock(fn):
    times = []
    for _ in range(4):
        torch.mps.synchronize()
        t = perf_counter()
        fn()
        torch.mps.synchronize()
        times.append((perf_counter() - t) * 1000)
    return median(times[1:])


def new_policy(model, seed, i, flip, budget):
    def issue(client, z, program, unused):
        data = inputs(z, False)
        state = joint.prepare(model, data)
        rng = np.random.default_rng([seed, i, flip, 1741])
        original = np.random.default_rng([seed, i, flip, 81])
        for at in range(0, budget, 32):
            count = min(budget - at, 32)
            u = old.noise(rng, count, len(z["banks"]))
            u[:, :, :, 0, 0] = torch.from_numpy(
                original.random((1, count, len(z["banks"]))).astype(np.float32)
            ).to(u.device)
            ids = joint.draw(data, state, u)[0].cpu().tolist()
            submit(
                client,
                [
                    Cell(
                        z["rule"],
                        tuple(bank[p] for bank, p in zip(z["addrs"], row, strict=True)),
                    )
                    for row in ids
                ],
                32,
            )
        return budget

    return issue


def live(a):
    rows = []
    for n, valid, flip, density, i, d in suite(a):
        if density != 1:
            continue
        seed = a.seeds[flip % len(a.seeds)]
        m = frozen(a, seed)
        reference = native(a, d, "reference", "-")["state_sha"]
        for budget in [1, 32] if valid == 1 else [4, 32]:
            for block in range(2):
                arms = ["shared-score", "joint"]
                if (block + flip) % 2:
                    arms.reverse()
                for arm in arms:
                    gen = (
                        new_policy(m, seed, i, flip, budget)
                        if arm == "joint"
                        else policy(m, arm, seed, i, flip, budget)
                    )
                    addr = 93007 + i * 32771 + flip + seed
                    row = trial(a, d, arm, m, seed, address_seed=addr, generate=gen)
                    assert row["paid"] == budget and (row["graph"] == reference) == (
                        row["ops"] == valid
                    )
                    row.pop("receipts")
                    rows.append(
                        dict(
                            row,
                            n=n,
                            valid=valid,
                            flip=flip,
                            block=block,
                            coverage=row["ops"] / valid,
                            reference=reference,
                            address_seed=addr,
                        )
                    )
        records(a.out / "native.csv", rows)
        print("live", n, valid, flip, flush=True)


def evaluate(a):
    from head_joint_audit import diagnose

    rows = []
    from partner_index_worlds import folder

    previous = copy(a)
    previous.out = a.selective.parent / "partner-index"
    extra = [
        (32768, 1, f, 1.0, i, folder(previous, ("hard", 32768, i, f)))
        for i in range(511001, 511004)
        for f in (0, 1)
    ]
    for n, valid, flip, density, i, d in [*suite(a), *extra]:
        z = read_packet(d / "binding.pkl")
        assert len(z["gold"]) == valid
        root = z["gold"][0][0]
        for seed in a.seeds:
            m = frozen(a, seed)
            data = inputs(z, False)
            prior = m.local.root_prior(data[0])[0]
            old_state = old.prepare(m, data)
            a_scores = prior + old_state[0][0][0]
            old_edge = old_state[1][0]
            u = old.noise(np.random.default_rng([seed, n, flip]), 1024, 2)
            state = joint.prepare(m, data)
            edge = state[1][0]
            p = state[0][0]
            samples = joint.draw(data, state, u)[0].cpu().numpy()
            winners = set(map(tuple, z["gold"]))

            distractor = old_edge.partner
            _, weights = joint.entries(
                tuple(joint.halves(distractor)), edge.index.dictionaries
            )
            index = edge.index
            units = index.ends.diff()[0]
            nonzero = index.keys[0][units > 0]
            collisions = int((nonzero[1:] == nonzero[:-1]).sum())
            # Dense one-root product law is diagnostic only.
            root_ix = torch.full((1, 1), root, device=p.device, dtype=torch.long)
            true_kernel = old.head_affinities(
                old.take(old_edge.query, root_ix), old_edge.partner
            )[0].prod(0)
            actual_partners = [row[1] for row in z["gold"]]
            conditional = float(
                (true_kernel[actual_partners].sum() / true_kernel.sum())
                * (1 - old.EXPLORE)
                + old.EXPLORE * valid / n
            )
            row = {
                "n": n,
                "valid": valid,
                "flip": flip,
                "density": density,
                "filler": i,
                "seed": seed,
                "product_wrong_positive": int((true_kernel > 0).sum()) - valid,
                "joint_rank": int((p > p[root]).sum()) + 1,
                "joint_conditional": conditional,
                "A_rank": int((a_scores > a_scores[root]).sum()) + 1,
                "A_prob": float(a_scores.softmax(0)[root]),
                "joint_prob": float(p[root]),
                "hits": sum(tuple(row) in winners for row in samples),
                "draws": len(samples),
                "distinct": len(set(map(tuple, samples)) & winners),
                "nnz": int((weights > 0).sum()),
                "positive_postings": len(nonzero),
                "collision_excess": collisions,
                "index_bytes": sum(
                    t.nbytes
                    for t in (*index.dictionaries, index.keys, index.ends, index.owners)
                ),
                "root_cache_bytes": sum(
                    t.nbytes for t in (edge.start, edge.count, edge.mass)
                ),
            }
            row.update(
                diagnose(
                    old_edge.query,
                    old_edge.partner,
                    prior.cpu().numpy(),
                    float(m.local.strength.exp()),
                    root,
                    edge.mass.sum(-1)[0].cpu().numpy(),
                )
            )
            rows.append(row)
        records(a.out / "frozen.csv", rows)
        print("frozen", n, valid, flip, density, flush=True)


def measure_page(m, data, u, arm, z, n):
    def make():
        if arm == "joint":
            return joint.prepare(m, data)
        future, edges = old.prepare(m, data)
        if arm == "shared-cached":
            root = (m.local.root_prior(data[0]) + future[0]).softmax(-1)
            return root, edges
        return future, edges

    def dec(state):
        if arm == "joint":
            return joint.draw(data, state, u)
        if arm == "shared-cached":
            root, edges = state
            refs = [old.categorical(root, u[:, :, 0, 0, 0])]
            for j, (parent, _) in enumerate(data[1], 1):
                selected, _ = old.conditional(
                    edges[j - 1],
                    refs[parent],
                    u[:, :, j],
                    "shared-score",
                    m.local.strength,
                )
                refs.append(selected)
            return torch.stack(refs, -1)
        return old.draw(m, data, state, u, arm)

    st = make()

    if arm == "shared-cached":
        reference = old.draw(m, data, old.prepare(m, data), u, "shared-score")[0]
        torch.testing.assert_close(dec(st), reference)

    def page():
        return dec(make())

    row = {
        "n": n,
        "arm": arm,
        "pack_ms": clock(lambda: inputs(z, False)),
        "rebuild_ms": clock(make),
        "decode_ms": clock(lambda: dec(st)),
        "page_ms": clock(page),
    }
    torch.mps.synchronize()
    with AllocationTrace() as trace:
        page()
    torch.mps.synchronize()
    return dict(
        row, dispatch_peak_bytes=trace.peak - trace.initial, dispatches=trace.calls
    )


def cost(a):
    rows = []
    for n, valid, flip, density, i, d in suite(a):
        if (valid, flip, density) != (1, 0, 1.0):
            continue
        z = read_packet(d / "binding.pkl")
        m = frozen(a, a.seeds[0])
        data = inputs(z, False)
        u = old.noise(np.random.default_rng(405), 32, 2)
        for arm in ("shared-score", "shared-cached", "joint"):
            rows.append(measure_page(m, data, u, arm, z, n))
        records(a.out / "cost.csv", rows)
        print("cost", n, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        {"evaluate": evaluate, "live": live, "cost": cost}[a.task](a)
