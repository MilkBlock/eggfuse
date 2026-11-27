"""Frozen-kernel diagnostics and separate, search-free CCP executions."""

import numpy as np
import torch
from binding_model import tensor, read_packet
from binding_online import trial
from completion_context import native
from credit_scale_buffer import submit
from discrete_draft import Cell
from first_parent import records
from selective_kernel import view
from selective_trials import inputs
from partner_index_worlds import args, cases, folder, frozen
from partner_index import (
    prepare,
    draw,
    conditional,
    take,
    dense_kernel,
    noise,
    EXPLORE,
    ATTEMPTS,
)

ARMS = ("legacy", "linear", "refined")


def dense_law(k, weights):
    """Diagnostic distribution only, for one supplied root."""
    p = k * weights
    if float(p.sum()) == 0:
        return torch.ones_like(p) / p.numel(), torch.ones_like(p) / p.numel(), 0.0
    p = p / p.sum()
    a = (p * k.pow(3)).sum()
    target = p * k.pow(3) / a.clamp_min(1e-30)
    fail = (1 - a) ** ATTEMPTS
    return (
        (1 - EXPLORE) * p + EXPLORE / p.numel(),
        (1 - EXPLORE) * ((1 - fail) * target + fail * p) + EXPLORE / p.numel(),
        float(fail),
    )


@torch.no_grad()
def evaluate(a):
    rows = []
    for seed in a.seeds:
        m = frozen(a, seed)
        for c in cases():
            mode, n, i, f = c
            z = read_packet(folder(a, c) / "binding.pkl")
            gold = z["gold"]
            root = gold[0][0]
            v = [r[1] for r in gold]
            root_ix = tensor(np.array([[root]]))
            data = inputs(z, False)
            future, edges = prepare(m, data)
            edge = edges[0]
            prior = m.local.root_prior(data[0])
            root_prob = float((future[0] + prior).softmax(-1)[0, root])
            # Compare original nonlinear first-parent readout to a truly additive prior.
            from selective_kernel import read_index

            additive = read_index(edge.query, edge.index[:2]).mean(-1)
            linear_root = float((prior + (additive + 1e-10).log()).softmax(-1)[0, root])
            legacy = m.local.relation(view(data[0], 0, 1), root_ix)[0, 0].softmax(-1)
            k = dense_kernel(edge, root_ix)[0]
            l, r, fail = dense_law(k, torch.ones_like(k))
            wids, wv = take(edge.query, root_ix)
            rid, rv = edge.partner
            heads = (
                (wids.unsqueeze(-1) == rid.unsqueeze(-2))
                * wv.unsqueeze(-1)
                * rv.unsqueeze(-2)
            ).sum((-2, -1))
            strength = m.local.strength.exp()
            fully = (
                ((heads + 1e-5).log() - heads.log1p())
                .sum(1)
                .mul(strength)
                .softmax(-1)[0]
            )
            mask = torch.zeros_like(k, dtype=torch.bool)
            mask[v] = True
            entries, scan, owners = edge.index
            # Quantify the finite-precision conditional law implemented by the scan.
            delta = scan.diff(dim=-1)
            mass = k.new_zeros(n)
            for head in range(entries.size(1)):
                for term in range(2):
                    part = (
                        (entries[0, head] == wids[0, head, 0, term])
                        * delta[0, head]
                        * wv[0, head, 0, term]
                    )
                    mass.scatter_add_(0, owners[0, head].long(), part / 4)
            actual = (1 - EXPLORE) * mass / mass.sum() + EXPLORE / n
            common = dict(
                mode=mode,
                n=n,
                i=i,
                flip=f,
                seed=seed,
                root=root_prob,
                additive_root=linear_root,
                colliding_wrong=int(((k > 0) & (~mask)).sum()),
                valid=len(gold),
                wrong_mass=float(k[~mask].sum()),
                true_mass=float(k[mask].sum()),
                max_wrong=float(k[~mask].max()),
                tv_scan=float((l - actual).abs().sum() / 2),
                refinement_fallback=fail,
            )
            rng = np.random.default_rng([seed, i, f, 214])
            u = noise(rng, 1024, 1)[:, :, 0]
            for arm, prob in [
                ("legacy", legacy),
                ("dense-nonlinear", fully),
                ("linear", l),
                ("refined", r),
            ]:
                p = float(prob[v].sum())
                row = dict(
                    common,
                    arm=arm,
                    second=p,
                    complete=root_prob * p,
                    empirical="",
                    distinct_reads="",
                    distinct_valid="",
                )
                if arm in ("linear", "refined"):
                    ix, reads = conditional(edge, root_ix.expand(1, 1024), u, arm)
                    page = reads[0].reshape(32, -1).cpu().numpy()
                    row.update(
                        empirical=float(mask[ix].float().mean()),
                        distinct_reads=np.mean([len(np.unique(q)) for q in page]),
                        distinct_valid=len(set(ix.flatten().tolist()) & set(v)),
                    )
                rows.append(row)
        records(a.out / "frozen.csv", rows)
        print("frozen", seed, len(rows), flush=True)


def policy(m, arm, seed, i, f, budget):
    def issue(client, z, program, unused):
        data = inputs(z, False)
        state = (m.flow(*data), None) if arm == "legacy" else prepare(m, data)
        rng = np.random.default_rng([seed, i, f, 1741])
        legacy_rng = np.random.default_rng([seed, i, f, 81])
        for offset in range(0, budget, 32):
            count = min(32, budget - offset)
            u = noise(rng, count, len(z["banks"]))
            original = legacy_rng.random((1, count, len(z["banks"]))).astype(np.float32)
            u[:, :, :, 0, 0] = tensor(
                original
            )  # original paired root; original legacy conditional RNG
            refs, _ = draw(m, data, state, u, arm)
            cells = [
                Cell(z["rule"], tuple(z["addrs"][j][p] for j, p in enumerate(ids)))
                for ids in refs[0].cpu().tolist()
            ]
            submit(client, cells, 32)
        return budget

    return issue


@torch.no_grad()
def live(a):
    models = {seed: frozen(a, seed) for seed in a.seeds}
    rows = []
    for c in cases():
        mode, n, i, f = c
        seed = a.seeds[(i - 511000) % len(a.seeds)]
        d = folder(a, c)
        reference = native(a, d, "reference", "-")["state_sha"]
        goal = 8 if mode == "multi" else 1
        budgets = [1, 32] if mode == "hard" else [4, 16, 32, 128]
        for b in budgets:
            # One-token replication on every held-out world. Full paired timings on
            # a common subset, alternating order within and across programs.
            if b != 1 and mode == "hard" and i >= 511002:
                continue
            if b not in (1, 32) and n == 32768 and i > 511000:
                continue
            blocks = (0, 1) if b == 32 else (0,)
            for block in blocks:
                arms = ARMS if (i + f + block) % 2 == 0 else reversed(ARMS)
                for arm in arms:
                    addr = 93007 + i * 32771 + f + seed
                    row = trial(
                        a,
                        d,
                        arm,
                        models[seed],
                        seed,
                        address_seed=addr,
                        generate=policy(models[seed], arm, seed, i, f, b),
                    )
                    assert (
                        row["paid"] == b
                        and 0 <= row["ops"] <= goal
                        and (row["graph"] == reference) == (row["ops"] == goal)
                    )
                    row.pop("receipts")
                    row.update(
                        n=n,
                        i=i,
                        flip=f,
                        mode=mode,
                        block=block,
                        coverage=row["ops"] / goal,
                        address_seed=addr,
                        reference=reference,
                    )
                    rows.append(row)
        records(a.out / "online.csv", rows)
        print("live", c, len(rows), flush=True)


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    with torch.no_grad():
        (live if a.task == "live" else evaluate)(a)
