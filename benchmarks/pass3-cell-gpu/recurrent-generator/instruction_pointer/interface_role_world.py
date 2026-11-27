"""Four baked computations, two entry relations, and an independent arithmetic Primitive."""

from cell_kv_world import World, compile_world
from value_read_world import filler_values, program


def mixed(a, actor, pool, swap, depth=2):
    bits = (0, 0, 1)
    first = program((swap, 0, 0), pool, bits, depth)
    second = program((1 - swap, 1, 1), pool + 100, bits, depth)
    for old, new in (
        ("Seed", "Noise"),
        ("Mid", "MidAlt"),
        ("(L", "(P"),
        ("(R", "(Q"),
        ("relation L", "relation P"),
        ("relation R", "relation Q"),
    ):
        second = second.replace(old, new)
    schedule = first.splitlines()[-1]
    lines = list(dict.fromkeys(first.splitlines()[:-1] + second.splitlines()[:-1]))
    vals = filler_values(pool)
    other = filler_values(pool + 100)
    lines += [
        f"(Seed {vals[2]} {vals[3]} {vals[2]})",
        f"(Noise {other[2]} {other[3]} {other[2]})",
        "(relation Bonus (i64 i64))",
        "(rule ((Seed x y z)) ((Bonus x (+ y z))) :ruleset root)",
        schedule,
    ]
    d = compile_world(
        a, f"interface-mixed-{pool}-{swap}-{depth}", "\n".join(lines) + "\n"
    )
    w = World(d, actor)
    alt = World(d, actor, sides="PQ", entry_table="MidAlt")
    for tid in range(alt.primitives, len(alt.layouts)):
        w.export_pc[len(w.layouts)] = alt.export_pc[tid]
        w.layouts.append(alt.layouts[tid])
    return w
