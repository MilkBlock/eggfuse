"""Native scalar probe versus direct draft selection on held cross-parent guards."""

from copy import deepcopy
from collections import Counter
import numpy as np
import torch
from torch.nn import functional as F
from address_scores import mlp
from binding_model import collate, tensor
from binding_online import trial
from cell_transaction import STATUS
from completion_context import native
from credit_scale_buffer import submit
from discrete_draft import Cell
from first_parent import load, records, sample


def drafts(net, z, rng, count):
    with torch.no_grad():
        noise = tensor(rng.random((1, count * 2, 2)).astype(np.float32))
        _, idx = net(collate([z]), draws=count * 2, noise=noise)
        return idx[0].cpu().numpy().reshape(count, 2, 2)


def features(z, ix):
    h = np.broadcast_to(z["h"], (*ix.shape[:2], 32))
    l, r = [z["banks"][j]["row"][ix[:, :, j]] for j in (0, 1)]
    return np.stack((h, l, r), axis=2).astype(np.float32)


def status_inputs(status):
    # Zero means no observation; other inputs are literal CCP receipt statuses.
    return F.one_hot((status + 1).long(), 32).float() * ((status >= 0)[..., None])


def logits(scorer, features, status, compute_allowed):
    h, left, right = features.unbind(2)
    q = (h + status_inputs(status)).tanh()
    proof = mlp(scorer, q, left, right, 0)
    if compute_allowed:
        return torch.cat((proof, mlp(scorer, q, left, right, 1)), 1)
    return proof


def compute(client, program, z, ix):
    rule = program["recipe"]["rules"][z["rule"]]
    [(pc, atom)] = [
        (pc, a) for pc, a in enumerate(rule["query"]) if "primitive" in a["call"]
    ]
    # Static operand roles from the chosen Recipe. Resolve only selected references.
    operands = [
        next(
            (j, c)
            for j, row in enumerate(z["slots"])
            for c, s in enumerate(row)
            if s == arg["slot"]
        )
        for arg in atom["args"][:-1]
    ]
    refs = np.array(
        [[(*z["addrs"][j][pair[j]], c) for j, c in operands] for pair in ix],
        dtype=np.int64,
    )
    return client.compute(z["rule"], pc, torch.from_numpy(refs))[:, 1].tolist()


def cells(z, ix):
    return [
        Cell(z["rule"], tuple(z["addrs"][j][p] for j, p in enumerate(pair)))
        for pair in ix
    ]


def corpus(a, net, seed):
    xs = []
    statuses = []
    valid = []
    same = []
    for i, d in enumerate(sorted((a.out / "worlds/guard-fit").iterdir())):

        def collect(client, z, program, rng):
            ix = drafts(net, z, rng, 16)
            pairs = ix.reshape(-1, 2)
            obs = compute(client, program, z, pairs)
            replies = submit(client, cells(z, pairs), 32)
            good = np.isin(
                [r[1] for r in replies],
                [STATUS.index("accepted"), STATUS.index("duplicate")],
            )
            # One target effect, virgin source Run, corroborate the physical duplicate.
            if good.any():
                assert len(set(map(tuple, pairs[good]))) == 1
            xs.extend(features(z, ix))
            statuses.extend(np.array(obs).reshape(-1, 2))
            valid.extend(good.reshape(-1, 2))
            same.extend((ix[:, 0] == ix[:, 1]).all(1))
            return len(pairs) * 2

        audit = trial(a, d, "audit", None, seed + i, generate=collect)
        assert audit["ops"] == int(np.asarray(valid[-16:]).any())
    return map(np.array, (xs, statuses, valid, same))


def fit(a, net, seed):
    x, obs, valid, same = corpus(a, net, seed)
    ids = np.flatnonzero(valid.any(1))
    assert len(ids) > 0 and np.all(obs[valid] == STATUS.index("computed"))
    x = tensor(x)
    models = {}
    logs = []
    for mode in ("direct", "active"):
        scorer = deepcopy(net.base.scorer)
        opt = torch.optim.AdamW(scorer.parameters(), lr=0.0004, weight_decay=0)
        rng = np.random.default_rng(seed)
        for epoch in range(12):
            losses = []
            for batch in np.array_split(rng.permutation(ids), max(1, len(ids) // 32)):
                y = np.array([rng.choice(np.flatnonzero(valid[i])) for i in batch])
                # In an unobserved draft supervise an actual verified scalar read on
                # 2/3 of traces and a verified direct primitive on the remaining third.
                want_query = rng.random(len(batch)) < 2 / 3
                inspected = rng.integers(2, size=len(batch))
                state = np.full((len(batch), 2), -1, dtype=np.int64)
                after = rng.random(len(batch)) < 0.5
                state[after, inspected[after]] = obs[batch[after], inspected[after]]
                fs = x[tensor(batch)]
                logps = []
                for mask, can_ask in [(~after, mode == "active"), (after, False)]:
                    if not mask.any():
                        continue
                    use = tensor(mask)
                    scores = logits(
                        scorer,
                        fs[use],
                        tensor(
                            state[mask]
                            if mode == "active"
                            else np.full_like(state[mask], -1)
                        ),
                        can_ask,
                    )
                    target = y[mask] + (2 * want_query[mask] if can_ask else 0)
                    lp = scores.log_softmax(-1)
                    idx = torch.arange(len(target), device="mps")
                    one = lp[idx, tensor(target)]
                    alias = lp[idx, tensor(target ^ 1)]
                    logps.append(
                        torch.where(
                            tensor(same[batch[mask]]), torch.logaddexp(one, alias), one
                        )
                    )
                loss = -torch.cat(logps).mean()
                opt.zero_grad()
                loss.backward()
                opt.step()
                losses.append(float(loss.detach()))
        models[mode] = scorer.eval()
        logs.append(
            dict(
                seed=seed,
                mode=mode,
                drafts=len(valid),
                supervised=len(ids),
                computed=int((obs == 14).sum()),
                guard=int((obs == 12).sum()),
                ce=np.mean(losses),
            )
        )
        torch.save(scorer.state_dict(), a.out / "weights" / f"{seed}-guard-{mode}.pt")
    return models, logs


@torch.no_grad()
def live_guard(a, net, scorer, seed, d, mode, block):
    stats = Counter()

    def generate(client, z, program, rng):
        budget = 32
        while budget:
            ix = drafts(net, z, rng, 1)
            fs = tensor(features(z, ix))
            state = np.full((1, 2), -1, dtype=np.int64)

            def choose(allowed):
                lp = logits(scorer, fs, tensor(state), allowed).log_softmax(-1)
                return int(sample(lp, tensor(rng.random(1).astype(np.float32))))

            choice = choose(mode != "direct")
            if choice >= 2:
                col = choice - 2
                [receipt] = compute(client, program, z, ix[0, col : col + 1])
                budget -= 1
                stats["compute"] += 1
                stats["computed"] += receipt == STATUS.index("computed")
                if not budget:
                    stats["pending"] += 1
                    break
                if mode == "active":
                    state[0, col] = receipt
                choice = choose(False)
            [reply] = submit(client, cells(z, ix[0, choice : choice + 1]), 1)
            if reply[1] == 0 and not stats["first_effect"]:
                stats["first_effect"] = 33 - budget
            stats["primitive"] += 1
            stats["guard_reject"] += reply[1] == STATUS.index("guard")
            stats["valid"] += reply[1] in (0, 1)
            budget -= 1
        return 32

    r = trial(a, d, mode, None, seed, generate=generate)
    r.pop("receipts")
    r.update(
        mode=mode,
        instance=d.name,
        block=block,
        coverage=r["ops"],
        **{
            k: stats[k]
            for k in (
                "compute",
                "computed",
                "primitive",
                "valid",
                "guard_reject",
                "pending",
                "first_effect",
            )
        },
    )
    return r


def guard(a):
    results = []
    training = []
    for seed in a.seeds:
        net = load(a, seed, "pool")
        if a.reuse_guard_weights:
            models = {}
            for mode in ("direct", "active"):
                scorer = deepcopy(net.base.scorer)
                scorer.load_state_dict(
                    torch.load(
                        a.out / "weights" / f"{seed}-guard-{mode}.pt", weights_only=True
                    )
                )
                models[mode] = scorer.eval()
        else:
            models, logs = fit(a, net, seed)
            training.extend(logs)
        for d in sorted((a.previous_binding / "worlds/cross-guard").glob("*-0")):
            reference = native(a, d, "capture", a.out / "guard-ref.json")["state_sha"]
            for block in (0, 1):
                for mode in (
                    ("direct", "active", "blind")
                    if not block
                    else ("blind", "active", "direct")
                ):
                    r = live_guard(
                        a, net, models.get(mode, models["active"]), seed, d, mode, block
                    )
                    assert r["ops"] in (0, 1) and (r["graph"] == reference) == bool(
                        r["ops"]
                    )
                    results.append(r)
        records(a.out / "guards.csv", results)
        if training:
            records(a.out / "guard-fit.csv", training)
        print("guard", seed, len(results), flush=True)
