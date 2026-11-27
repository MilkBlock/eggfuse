"""Matched native programs. Only one Seed scalar varies within each pair."""

import numpy as np

from cell_kv_world import World, compile_world


def source(
    depth,
    sides,
    jobs,
    distract,
    recipe_seed,
    instance,
    flip,
    fork=False,
    invert_guard=False,
    invert_op=False,
):
    recipe_rng = np.random.default_rng(recipe_seed)
    lines = []
    tables = {"Seed": 2, "Mid": 2, "Common": 2, "DoneL": 2, "Permit": 1}
    if distract:
        tables.update(Noise=2, Aux=2)
    for side in sides:
        for j in range(depth):
            tables[f"{side}{j}"] = 2
    for name, n in tables.items():
        lines.append(f"(relation {name} ({' '.join(['i64'] * n)}))")
    lines += ["(ruleset root)", "(rule ((Seed x y)) ((Mid x y)) :ruleset root)"]
    if distract:
        lines.append("(rule ((Noise x y)) ((Aux y x)) :ruleset root)")
    for j in range(depth):
        lines.append(f"(ruleset s{j})")
        for side in recipe_rng.permutation(list(sides)):
            pred = "Mid" if j == 0 else f"{side}{j - 1}"
            equal = (side == "L") != invert_guard
            guard = f" ({'=' if equal else '!='} x y)"
            if len(sides) == 3:
                guard = " (= x 0)" if side == "T" else guard + " (!= x 0)"
            op = "+" if (side == "L") != invert_op else "-"
            join = " (Mid x u)" if fork and j == depth - 1 and j > 0 else ""
            arg = "(max y u)" if join else "y"
            lines.append(
                f"(rule (({pred} x y){guard if j == 0 else ''}{join}) (({side}{j} x ({op} {arg} {j + 1}))) :ruleset s{j})"
            )
    lines.extend(["(ruleset export)", "(ruleset finish)"])
    for side in sides:
        lines.append(f"(rule (({side}{depth - 1} x y)) ((Common x y)) :ruleset export)")
    lines.append("(rule ((Common x y) (Permit x)) ((DoneL x y)) :ruleset finish)")
    rng = np.random.default_rng(instance)
    vals = rng.choice(2**27 - 1, 4 * jobs, replace=False).reshape(jobs, 4) + 1
    facts = []
    for i, (x, y, u, v) in enumerate(vals):
        if i == 0:
            y = y if flip else x
        elif i == 1 and len(sides) == 3:
            x = 0
        elif i % 2 == 0:
            y = x
        facts.extend([f"(Seed {x} {y})", f"(Permit {x})"])
        if distract:
            facts.append(f"(Noise {u} {v})")
    rng.shuffle(facts)
    return (
        "\n".join(
            [
                *lines,
                *facts,
                "(run-schedule (run root) "
                + " ".join(f"(run s{j})" for j in range(depth))
                + " (run export) (run finish) (run finish))",
            ]
        )
        + "\n"
    )


def cases(split):
    if split == "fit":
        for i in range(24):
            level = i % 3
            yield (
                f"fit-{i}",
                (
                    1 + level,
                    "LR" if level < 2 else "LRT",
                    1 if level == 0 else 2 + level,
                    level > 0,
                    100 + level,
                    987004 + i,
                ),
            )
    else:
        for i in range(12):
            level = i % 3
            novel = i >= 6
            yield (
                f"{'new' if novel else 'seen'}-{i}",
                (
                    4 + level if novel else 1 + level,
                    "LR" if level < 2 else "LRT",
                    1 if level == 0 else 2 + level,
                    level > 0,
                    900 + level if novel else 100 + level,
                    752913 + i,
                    novel and level > 0,
                ),
            )


def world(a, actor, name, spec, flip):
    depth, sides, jobs, dist, rs, inst, *fork = spec
    return World(
        compile_world(
            a,
            name + "-" + str(int(flip)),
            source(depth, sides, jobs, dist, rs, inst, flip, *fork),
        ),
        actor,
        sides,
    )
