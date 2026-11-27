"""Post-freeze, offline native evidence and same-interface counterfactuals."""

from time import perf_counter

import numpy as np
import torch

from completion_context import read
from cell_kv_model import CellKV
from cell_kv_runtime import native
from cell_kv_study import checkpoint
from cell_kv_world import World, make
from first_parent import records
from partner_index_worlds import args
from rule_read import load_actor


def opposite_inputs(a, actor):
    for i in range(6):
        for flip in (False, True):
            yield (
                i,
                flip,
                World(
                    make(
                        a,
                        f"counter-{i}-{int(flip)}",
                        4 + i % 2,
                        1,
                        98211 + i * 41,
                        i % 2 == 1,
                        flip,
                    ),
                    actor,
                ),
            )


def swap_addresses(s):
    # Offline bijection on physical owners and references, preserving named wires.
    def uid(i):
        return 29711 - 7 * i

    def ref(r):
        return uid(r[0]), r[1], r[2]

    return dict(
        s,
        ports=[
            (ref(r), uid(owner), t, tab, fields, fwd, tuple(map(ref, parents)))
            for r, owner, t, tab, fields, fwd, parents in reversed(s["ports"])
        ],
    )


@torch.no_grad()
def counter(a):
    actor = load_actor(a.actor, True)
    worlds = []
    for i, flip, w in opposite_inputs(a, actor):
        ex, targets = native(a, w, teacher="higher")[0]
        gold, refs = next((tid, refs) for tid, refs in targets if tid >= w.primitives)
        worlds.append((i, flip, w, ex, gold, refs))
    rows = []
    for arm in "ABCD":
        for joint, steps in [(False, 0), (False, 360), (True, 360)]:
            for seed in (71, 113):
                net = CellKV(a, arm, joint).eval()
                if steps:
                    net.load_state_dict(
                        torch.load(
                            checkpoint(a, arm, joint, seed, steps), weights_only=True
                        )
                    )
                for i, flip, w, s, gold, refs in worlds:
                    net.prepare(w)
                    nodes, codes, types = net.cache
                    for root_only in (False, True):
                        if root_only:
                            x = codes.clone()
                            x[w.primitives :] = codes[w.root]
                            net.cache = nodes, x, types
                        mem = net.state(w, s)
                        renamed = net.state(w, swap_addresses(s))
                        alt = 2 * w.primitives + 1 - gold
                        pg = mem["lp"][mem["menu"].index(gold)].exp()
                        pa = mem["lp"][mem["menu"].index(alt)].exp()
                        gidx = mem["pos"][refs[0]]
                        bind = net.address(w, mem, gold, []).exp()[gidx]
                        altbind = net.address(w, mem, alt, []).exp()[gidx]
                        moved = net.address(w, renamed, gold, []).exp().flip((0,))
                        err = max(
                            float(
                                (moved - net.address(w, mem, gold, []).exp())
                                .abs()
                                .max()
                            ),
                            float((renamed["lp"].exp() - mem["lp"].exp()).abs().max()),
                        )
                        rows.append(
                            dict(
                                arm=arm,
                                joint=int(joint),
                                updates=steps,
                                seed=seed,
                                pair=i,
                                flip=int(flip),
                                structure_cosine=float(
                                    torch.cosine_similarity(
                                        net.cache[1][-2:-1], net.cache[1][-1:]
                                    )
                                ),
                                root_only=int(root_only),
                                gold=gold - w.primitives,
                                p_gold_h=float(pg),
                                p_other_h=float(pa),
                                conditional_template=float(pg / (pg + pa)),
                                p_binding_given_h=float(bind),
                                p_complete=float(pg * bind),
                                p_wrong_same_binding=float(pa * altbind),
                                permutation_max_abs=err,
                            )
                        )
    records(a.out / "counter.csv", rows)


@torch.no_grad()
def forced(a):
    # The correct template comes from a separate native replay and is used
    # exclusively in this one-shot diagnostic, never in native.json.
    actor = load_actor(a.actor, True)
    out = []
    for i, flip, w in opposite_inputs(a, actor):
        ex, targets = native(a, w, teacher="higher")[0]
        gold = next(t for t, _ in targets if t >= w.primitives)
        for arm in "ABCD":
            net = CellKV(a, arm, True).eval()
            net.load_state_dict(
                torch.load(checkpoint(a, arm, True, 71, 360), weights_only=True)
            )

            class OneShot:
                def prepare(self, world):
                    net.prepare(world)

                def generate(self, world, state, rng, slots):
                    if w.root not in state["menu"]:
                        return []
                    return net.generate(
                        world, dict(state, menu=[gold]) if hint else state, rng, 1
                    )

            for hint in (False, True):
                for draw in (193, 827):
                    r = native(a, w, policy=OneShot(), seed=draw, slots=1)
                    out.append(
                        dict(
                            pair=i,
                            flip=int(flip),
                            arm=arm,
                            given_template=int(hint),
                            draw=draw,
                            selected=r["stats"].get("higher_selected", 0),
                            opened=r["stats"].get("higher_opened", 0),
                            confirmed=r["stats"]["higher_completed"],
                            ops=r["ops"],
                            paid=r["stats"]["paid"],
                        )
                    )
        records(a.out / "oneshot.csv", out)


@torch.no_grad()
def size(a):
    net = CellKV(a, "D", True).eval()
    net.load_state_dict(
        torch.load(checkpoint(a, "D", True, 71, 360), weights_only=True)
    )
    out = []
    for depth in (3, 15, 63, 127, 255):
        start = perf_counter()
        d = make(a, f"scale-timed-{depth}", depth, 2, 156701, True)
        start = perf_counter()
        w = World(d, net.actor)
        bake_s = perf_counter() - start
        training = native(a, w, teacher="higher")
        state = training[0][0]
        start = perf_counter()
        net.prepare(w)
        cold = perf_counter() - start
        nodes, codes, types = net.cache
        for block in range(3):
            start = perf_counter()
            net.prepare(w)
            warm = perf_counter() - start
            start = perf_counter()
            net.generate(w, state, np.random.default_rng(81), 32)
            gen = perf_counter() - start
            out.append(
                dict(
                    steps=depth + 1,
                    external=1,
                    templates=len(state["menu"]),
                    owners=len({v[1] for v in state["ports"]}),
                    ports=len(state["ports"]),
                    block=block,
                    catalog_s=bake_s,
                    **read(d / "preparation.json"),
                    cold_encode_ms=1000 * cold,
                    cached_read_us=1e6 * warm,
                    template_code_B=codes[-1].nbytes,
                    whole_catalog_code_B=codes.nbytes,
                    generate_32_ms=1000 * gen,
                    max_exposed_ports=max(len(s["ports"]) for s, _ in training),
                )
            )
        records(a.out / "size.csv", out)
        print("scale", depth, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"evaluate": counter, "cost": size, "live": forced}[a.task](a)
