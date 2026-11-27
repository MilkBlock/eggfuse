"""Fresh post-checkpoint Higher bodies and rules; free generation in native environments."""

import json

import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from foundation_world import source
from int_parameters import StructuralBake, digest
from joint_cell_corpus import folder
from joint_cell_train import fitted
from partner_index_worlds import args
from trigger_execution import ExecutionTrace
from variable_completion import CompletionPolicy


def create(a, net, arity):
    depth = 8
    program = source(depth, 4, arity, 898317 + arity)
    # Fresh arithmetic at the last step: both new bodies and new rule structures.
    old = program.count("(+ y ")
    for mult in range(1, 5):
        program = program.replace(f"(+ y {mult * depth})", f"(* y {mult * depth})")
    assert program.count("(+ y ") < old
    ir = compile_world(a, f"joint-cell-all-weights-frozen-{arity}", program)
    w = World(ir, net.actor, entry_table="Mid", sides="")
    for side in "LRUV":
        body = list(w.layouts[w.root])
        prev = "Mid"
        for j in range(depth):
            name = f"{side}{j}"
            rid = w.outnames[name]
            body.append((rid, len(body), [(j, w.outputs[body[-1][0]][prev])]))
            prev = name
        w.export_pc[len(w.layouts)] = w.outputs[body[-1][0]][prev]
        w.layouts.append(body)
    return w


def run(a):
    rows = []
    for arm in ("small", "expanded", "replay", "sweep"):
        for seed in (71, 113):
            n = fitted(a, "fact", arm, seed)
            for arity in (1, 2):
                w = create(a, n, arity)
                shape = StructuralBake(w.prog)
                for draw in (193, 307):
                    obs = ExecutionTrace()
                    pol = CompletionPolicy(n, True, None, False)
                    x = native(
                        a,
                        w,
                        policy=pol,
                        slots=6,
                        submit_pages=2,
                        seed=draw,
                        rule_state=True,
                        receipt_memory=True,
                        execution_trace=obs,
                    )
                    rows.append(
                        dict(
                            arm=arm,
                            seed=seed,
                            draw=draw,
                            arity=arity,
                            metrics=x,
                            signatures=[
                                digest(shape.describe(t)[0])
                                for t in w.layouts[w.primitives :]
                            ],
                            higher=list(obs.higher.values()),
                        )
                    )
    (folder(a) / "new-higher.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
