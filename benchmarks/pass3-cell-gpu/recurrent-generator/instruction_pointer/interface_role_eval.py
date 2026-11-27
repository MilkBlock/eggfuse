"""Paired physical, semantic, and mixed native tests with the same frozen policies."""

import copy
import json
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World
from interface_role_model import RoleRead
from interface_role_train import dest
from interface_role_world import mixed
from operand_read_eval import fixture
from partner_index_worlds import args
from value_read_eval import Observe
from value_read_train import SEEDS, STEPS
from value_read_world import CUBES, SCHEMAS, filler_values, key


def load(a, arm, seed):
    model = RoleRead(a, arm).eval()
    file = (
        a.out / "operand-read" / f"D-{seed}-{STEPS}.pt"
        if arm == "A"
        else dest(a) / f"{arm}-{seed}-{STEPS}.pt"
    )
    model.load_state_dict(torch.load(file, weights_only=True))
    return model


def distribution(net, w, s):
    mem = net.state(w, s)
    # Only used in offline diagnostics. Every template here has exactly one named input.
    assert all(len(w.roles[w.layouts[t][0][0]]) == 1 for t in s["menu"])
    all_lp = torch.stack(
        [mem["lp"][j] + net.address(w, mem, t, []) for j, t in enumerate(mem["menu"])]
    )
    probs = all_lp.exp()
    torch.testing.assert_close(probs.sum(), probs.new_ones(()))
    return mem, all_lp, probs


def diagnostic(net, w, s, targets):
    net.prepare(w)
    net.audit = True
    root_t, refs = next(tok for tok in targets if tok[0] >= w.primitives)
    results = []
    base = None
    for name, layout, hard in (
        ("canonical", ("train", 0), False),
        ("perm0", ("held", 0), False),
        ("perm1", ("held", 1), False),
        ("hard", ("held", 0), True),
    ):
        if hard and (net.arm_name != "C" or len(s["ports"]) != 1):
            continue
        net.hard = hard
        net.physical = layout
        mem, lp, probs = distribution(net, w, s)
        if base is None:
            base = probs.detach()
        mt = mem["menu"]
        pos = mem["pos"]
        gold = [(mt.index(t), pos[r[0]]) for t, r in targets]
        target_index = (mt.index(root_t), pos[refs[0]])
        branch = [mt.index(t) for t in range(w.primitives, len(w.layouts))]
        col = target_index[1]
        pred = int(lp[branch, col].argmax())
        all_mass = sum(probs[j, k] for j, k in set(gold))
        one = probs[target_index]
        row = {
            "layout": name,
            "max_delta": float((probs - base).detach().abs().max()),
            "tv": float((probs - base).abs().sum().detach() / 2),
            "valid_mass": float(all_mass.detach()),
            "p_full": float(one.detach()),
            "pick": pred,
            "gold": root_t - w.primitives,
            "correct": pred == root_t - w.primitives,
        }
        if net.arm_name == "C" and not hard:
            query, keys, values, rel, wt, ids = net.role_trace
            tensors = (
                query,
                keys,
                values,
                rel,
                net.actor.input_role.weight,
                net.actor.query.weight,
            )
            row["grads"] = [
                float(x.norm()) for x in torch.autograd.grad(-lp[target_index], tensors)
            ]
            weights = wt[col, mt.index(root_t)].detach()
            index = net.columns[root_t]
            if (index >= 0).all():
                row["read_mass"] = float(
                    (weights * (ids[col, None, :] == index[:, None])).sum(-1).mean()
                )
        results.append(row)
    net.audit = net.hard = False
    return results


def evaluate(a, labels=("known", "new_wire", "width", "shift", "deep", "mixed")):
    nets = {(arm, seed): load(a, arm, seed) for arm, seed in product("ABC", SEEDS)}
    actor = nets["A", 71].actor
    sigs = set()
    for s in SCHEMAS:
        sigs.update(digest(World(a.out / "worlds" / key(s, 71001, CUBES[0]), actor)))
    train_values = set().union(*(set(filler_values(p)) for p in range(72001, 72033)))
    for label in labels:
        diag = []
        live = []
        pools = range(81011, 81015) if label == "known" else range(124081, 124084)
        specs = (
            product(pools, range(2), range(2), CUBES)
            if label != "mixed"
            else ((p, 0, 0, (0, 0, 1)) for p in pools)
        )
        for pool, g, o, bits in specs:
            assert train_values.isdisjoint(filler_values(pool))
            if label == "mixed":
                assert train_values.isdisjoint(filler_values(pool + 100))
            prev = None
            for wire in (2,) if label == "new_wire" else (0, 1):
                with TemporaryDirectory() as tmp:
                    local = copy.copy(a)
                    if label != "known":
                        local.out = Path(tmp)
                    w = (
                        mixed(local, actor, pool, wire)
                        if label == "mixed"
                        else fixture(
                            local,
                            actor,
                            {
                                "known": "known",
                                "new_wire": "position",
                                "width": "width",
                                "shift": "shift",
                                "deep": "deep",
                            }[label],
                            (wire, g, o),
                            pool,
                            bits,
                        )
                    )
                    signatures = digest(w)
                    if label != "known":
                        assert sigs.isdisjoint(signatures)
                    s, ts = native(a, w, teacher="higher")[0]
                    if prev is not None:
                        assert prev == s
                    prev = s
                    meta = {
                        "label": label,
                        "pool": pool,
                        "g": g,
                        "o": o,
                        "bits": list(bits),
                        "wire": wire,
                        "templates": len(s["menu"]),
                        "owners": len({p[1] for p in s["ports"]}),
                        "signatures": signatures,
                    }
                    for (arm, seed), net in nets.items():
                        diag.extend(
                            dict(**meta, arm=arm, seed=seed, **r)
                            for r in diagnostic(net, w, s, ts)
                        )
                    corners = (
                        ((0, 0, 1), (0, 0, 0))
                        if label == "new_wire"
                        else ((0, 0, 1), (0, 1, 0))
                    )
                    if label == "mixed" or (pool == pools[0] and bits in corners):
                        for draw, block in product((193, 827), (0, 1)):
                            order = list(nets)
                            if (g + o + wire + block + (draw == 827)) % 2:
                                order.reverse()
                            for arm, seed in order:
                                net = nets[arm, seed]
                                net.physical = ("held", 0)
                                net.static_cache.clear()
                                policy = Observe(net)
                                with torch.no_grad():
                                    res = native(a, w, policy=policy, seed=draw)
                                state, tokens = policy.entry
                                # Translate offline gold to the independently randomized first window.
                                # Use full published table+hashes only AFTER policy execution.
                                address = {
                                    (p[3], tuple(p[4])): p[0] for p in state["ports"]
                                }
                                assert len(address) == len(state["ports"])
                                back = {
                                    p[0]: address[p[3], tuple(p[4])] for p in s["ports"]
                                }
                                gold = {(t, tuple(back[r] for r in rs)) for t, rs in ts}
                                valid = set(tokens) & gold
                                live.append(
                                    dict(
                                        **meta,
                                        arm=arm,
                                        seed=seed,
                                        draw=draw,
                                        block=block,
                                        valid=len(valid),
                                        higher_hits=sum(
                                            tok[0] >= w.primitives and tok in gold
                                            for tok in tokens
                                        ),
                                        primitive_hits=sum(
                                            tok[0] < w.primitives and tok in gold
                                            for tok in tokens
                                        ),
                                        slots=len(tokens),
                                        **res,
                                    )
                                )
                    for net in nets.values():
                        net.static_cache.clear()
        for name, rows in (("diag", diag), ("live", live)):
            (dest(a) / f"{label}-{name}.json").write_text(
                json.dumps(rows, separators=(",", ":"))
            )
        print(label, len(diag), len(live), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    evaluate(args())
