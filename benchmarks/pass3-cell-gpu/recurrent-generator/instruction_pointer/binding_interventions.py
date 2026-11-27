"""Matched native wiring and publication counterfactuals with frozen online inputs."""

from copy import deepcopy
import itertools
from pathlib import Path
import random
import numpy as np
import torch
from binding_worlds import build
from binding_packets import packet
from binding_model import Decoder, parser, collate, tensor, read_packet
from completion_context import read, write, native
from discovery_score import packet as request
from discrete_draft import Cell


def fixture(a, instance, layout, change):
    vals = random.Random(instance).sample(range(10**12, 10**13), 16)
    if layout == "condition":
        a1, b, c, d, e, a2, b2, c2, d2, e2 = vals[:10]
        rows = [(a1, b, c), (b, d, e), (a2, b2, c2), (b2, d2, e2)]
        header = """(datatype Tag (Mark i64) (Combined Tag Tag))
(function Price (i64) Tag :merge (Combined old new))
(relation Update (i64 i64))
(rule ((Update key val)) ((set (Price key) (Mark val))) :ruleset warm)"""
        source = f"{header}\n(set (Price {b}) (Mark {b}))\n(set (Price {b2}) (Mark {b2}))\n(Update {b} {vals[10] if change else b})\n(Update {b2} {vals[11]})\n"
        atoms = (
            "(Edge a b c) (Edge b d e) (= old (Mark b)) (= tag (Combined old later))"
        )
    else:
        a1, b, c, d, e, f, g, h = vals[:8]
        rows = [(a1, b, c), (b, d, e), (f, c, g), (h, vals[8], vals[9])]
        atoms = {
            "eq10": "(Edge a b c) (Edge b d e)",
            "eq21": "(Edge a b c) (Edge d c e)",
        }[layout]
        source = ""
    text = (
        "(relation Edge (i64 i64 i64))\n(ruleset warm)\n(ruleset probe)\n(relation Result (i64 i64))\n"
        + source
    )
    text += f"(rule ({atoms}) ((Result a e)) :ruleset probe)\n"
    text += (
        "\n".join(f"(Edge {x} {y} {z})" for x, y, z in rows)
        + "\n(run-schedule (run warm) (run probe))\n"
    )
    job = ("interventions", instance, 4, layout, change, False, False)
    build(a, job, override=text)
    path = a.out / "worlds/interventions" / f"0004-{layout}-{instance:05}-{change}"
    packet(a, path)
    return path


def alias_targets(a, d, z):
    """Only offline: test each equal-row substitution against canonical native effects."""
    tape = read(d / "prefix.json")
    physical = {}
    base = max([q["token"] for q in tape["requests"]] + [0]) + 1

    def verdict(ix):
        c = Cell(z["rule"], tuple(z["addrs"][j][v] for j, v in enumerate(ix)))
        f = d / "named-check.json"
        write(f, dict(tape, requests=tape["requests"] + [request(c, 2, base)]))
        rep = native(a, d, "replay", f, 2, "--ept-origins")
        return rep["state_sha"], dict(rep["ept"]["origins"]).get(base, 0)

    for ix in z["gold"]:
        group, gain = verdict(ix)
        assert gain > 0
        aliases = [
            np.flatnonzero((b["raw"] == b["raw"][v]).all(-1))
            for b, v in zip(z["banks"], ix)
        ]
        for alt in itertools.product(*aliases):
            if verdict(alt) == (group, gain):
                physical[tuple(alt)] = group
    return physical


@torch.no_grad()
def run(a):
    models = {}
    for seed in a.seeds:
        for arm in a.arms:
            net = Decoder(a, arm).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            models[seed, arm] = net
    stats = []
    outcomes = []
    for i in range(8):
        instance = 35000 + i
        worlds = [
            read_packet(fixture(a, instance, l, 0) / "binding.pkl")
            for l in ("eq10", "eq21")
        ]
        left, right = worlds
        assert left["addrs"] == right["addrs"] and np.array_equal(
            left["banks"][0]["raw"], right["banks"][0]["raw"]
        )
        assert len(left["gold"]) == len(right["gold"]) == 1
        ((anchor, l),) = left["gold"]
        ((same, r),) = right["gold"]
        assert same == anchor and l != r
        for (seed, arm), net in models.items():

            def logits(state):
                inp = collate([state])
                y = tensor(np.array([[[anchor, l]]]))
                h, roles, _, banks = inp
                updated = net.gru(banks[0][0][:, anchor] + roles[:, 0], h)
                q = (updated + roles[:, 1]).tanh()
                ps, _ = net(inp, y)
                return ps[1][0, 0].exp().cpu().numpy(), q

            pl, ql = logits(left)
            pr, qr = logits(right)
            swap = deepcopy(left)
            swap["wires"] = right["wires"]
            pw, _ = logits(swap)
            # Transplant one field identity while leaving the whole-row key,
            # owner, static Recipe, previous binding and other fields unchanged.
            v = deepcopy(left)
            bank = v["banks"][1]["hash"]
            bank[[l, r], 0] = bank[[r, l], 0]
            moved, _ = logits(v)
            v = deepcopy(left)
            bank = v["banks"][1]["hash"]
            bank[[l, r], 2] = bank[[r, l], 2]
            irrelevant, _ = logits(v)
            stats.append(
                dict(
                    seed=seed,
                    arm=arm,
                    instance=instance,
                    left=float(pl[l]),
                    right=float(pr[r]),
                    right_before=float(pl[r]),
                    only_wiring=float(pw[r]),
                    field_transplant=float(moved[r]),
                    unrelated=float(irrelevant[l]),
                    both_argmax=int(pl.argmax() == l and pr.argmax() == r),
                    query_change=float((ql - qr).norm()),
                    whole_key_change=float(
                        np.linalg.norm(
                            left["banks"][0]["row"] - right["banks"][0]["row"]
                        )
                    ),
                )
            )
        for changed in (0, 1):
            d = fixture(a, instance, "condition", changed)
            z = read_packet(d / "binding.pkl")
            gold = alias_targets(a, d, z)
            inp = collate([z])
            tape = read(d / "prefix.json")
            for (seed, arm), net in models.items():
                noise = (
                    np.random.default_rng(seed + i)
                    .random((1, 64, len(z["slots"])))
                    .astype(np.float32)
                )
                _, picks = net(inp, draws=64, noise=tensor(noise))
                picks = list(map(tuple, picks[0].cpu().tolist()))
                base = max([q["token"] for q in tape["requests"]] + [0]) + 1
                cells = [
                    Cell(z["rule"], tuple(z["addrs"][j][t] for j, t in enumerate(ix)))
                    for ix in picks
                ]
                f = d / "sample.json"
                write(
                    f,
                    dict(
                        tape,
                        requests=tape["requests"]
                        + [request(c, 2, base + j) for j, c in enumerate(cells)],
                    ),
                )
                rep = native(a, d, "replay", f, 2, "--ept-origins")
                effective = sum(g for uid, g in rep["ept"]["origins"] if uid >= base)
                assert effective == len({gold[ix] for ix in picks if ix in gold})
                outcomes.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        changed=changed,
                        instance=i,
                        targets=len(set(gold.values())),
                        physical=len(gold),
                        effective=effective,
                        hits=sum(ix in gold for ix in picks),
                        draws=64,
                        native=rep["counts"],
                    )
                )
    write(a.out / "interventions.json", stats)
    write(a.out / "conditional.json", outcomes)


if __name__ == "__main__":
    p = parser()
    p.add_argument("--compiler", type=Path, required=True)
    torch.set_num_threads(1)
    run(p.parse_args())
