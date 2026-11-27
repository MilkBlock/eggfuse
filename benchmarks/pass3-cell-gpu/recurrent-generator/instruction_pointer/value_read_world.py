"""Fully crossed three-field tables for native conditional computation selection."""

from itertools import product

import numpy as np

from cell_kv_world import World, compile_world

SCHEMAS = list(product(range(2), range(2), range(2)))
CUBES = tuple(product(range(2), repeat=3))


def field_pair(wiring):
    return ((0, 1), (0, 2), (1, 2))[wiring]


def filler_values(pool):
    return np.random.default_rng(pool).choice(2**27 - 1, 5, replace=False) + 1


def program(schema, pool, bits, depth=1, distract=False):
    wiring, rev_guard, rev_op = schema
    v = "xyz"
    left, right = field_pair(wiring)
    lines = [
        "(relation Seed (i64 i64 i64))",
        "(relation Mid (i64 i64 i64))",
        "(relation Common (i64 i64))",
        "(relation DoneL (i64 i64))",
    ]
    for side in "LR":
        for j in range(depth):
            lines.append(f"(relation {side}{j} (i64 i64))")
    lines += ["(ruleset root)", "(rule ((Seed x y z)) ((Mid x y z)) :ruleset root)"]
    if distract:
        lines += [
            "(relation Noise (i64 i64 i64))",
            "(relation Aux (i64 i64))",
            "(rule ((Noise x y z)) ((Aux y z)) :ruleset root)",
        ]
    for j in range(depth):
        lines.append(f"(ruleset s{j})")
        for idx, side in enumerate("LR"):
            pred = "(Mid x y z)" if j == 0 else f"({side}{j - 1} x y)"
            cmp = "=" if idx == rev_guard else "!="
            guard = f" ({cmp} {v[left]} {v[right]})" if j == 0 else ""
            op = "+" if idx == rev_op else "-"
            arg = "z" if j == 0 else str(j + 1)
            lines.append(
                f"(rule ({pred}{guard}) (({side}{j} x ({op} y {arg}))) :ruleset s{j})"
            )
    lines += ["(ruleset export)", "(ruleset finish)"]
    lines += [
        f"(rule (({side}{depth - 1} x y)) ((Common x y)) :ruleset export)"
        for side in "LR"
    ]
    lines.append("(rule ((Common x y)) ((DoneL x y)) :ruleset finish)")
    values = filler_values(pool)
    lines.append("(Seed " + " ".join(str(values[b]) for b in bits) + ")")
    if distract:
        lines.append("(Noise " + " ".join(map(str, values[2:])) + ")")
    return (
        "\n".join(
            [
                *lines,
                "(run-schedule (run root) "
                + " ".join(f"(run s{j})" for j in range(depth))
                + " (run export) (run finish) (run finish))",
            ]
        )
        + "\n"
    )


def key(schema, pool, bits, depth=1, distract=False):
    return f"r{''.join(map(str, schema))}-d{depth}-n{int(distract)}-v{pool}-b{''.join(map(str, bits))}"


def instance(a, actor, schema, pool, bits, depth=1, distract=False):
    return World(
        compile_world(
            a,
            key(schema, pool, bits, depth, distract),
            program(schema, pool, bits, depth, distract),
        ),
        actor,
    )


def prepare(a):
    import torch

    from cell_kv_runtime import native
    from rule_read import load_actor

    actor = load_actor(a.actor, True)
    corpus = {}
    for schema in SCHEMAS:
        for pool in range(71001, 71007):
            for bits in CUBES:
                w = instance(a, actor, schema, pool, bits)
                rows = native(a, w, teacher="higher")
                (t,) = [t for t, r in rows[0][1] if t >= w.primitives]
                j, k = field_pair(schema[0])
                assert t - w.primitives == (schema[1] ^ (bits[j] != bits[k]))
                corpus[w.dir.name] = rows
    torch.save(corpus, a.out / "corpus.pt")


if __name__ == "__main__":
    import torch

    from partner_index_worlds import args

    torch.set_num_threads(1)
    prepare(args())
