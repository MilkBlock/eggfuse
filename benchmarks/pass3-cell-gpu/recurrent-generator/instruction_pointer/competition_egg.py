"""Held-out native EggCC transfer, using the historical constructor-aligned coverage contract."""

import json
import os
import subprocess

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_corpus import out
from competition_draw import Policy
from partner_index_worlds import args
from recursive_coverage import Target
from selected_cell_study import model, store


def network(a, arm, seed):
    net = model(a, seed, "direct", True)
    if arm == "prior":
        return net
    if arm == "previous":
        return model(a, seed, "direct", True, "curriculum")
    net.load_state_dict(torch.load(out(a) / f"{arm}-{seed}.pt", weights_only=True))
    return net


def egg(a, case):
    d = out(a) / "egg" / case
    d.mkdir(parents=True, exist_ok=True)
    ir = d / "program.json"
    if not ir.exists():
        ir.symlink_to((a.data / case / "program.json").resolve())
    for name, cmd in (
        ("contract", ["receipt-contract", ir]),
        ("capture", ["reference", ir, "-", "time", "--export", d / "reference.json"]),
        (
            "initial-report",
            ["reference", ir, "-", "time", "0", "--export", d / "initial.json"],
        ),
    ):
        p = d / f"{name}.json"
        if not p.exists():
            p.write_bytes(subprocess.check_output([a.runtime_binary, *cmd]))
    ref = Target(
        json.loads(ir.read_text()), json.loads((d / "reference.json").read_text())
    )
    initial = ref.match(json.loads((d / "initial.json").read_text()))
    goal = set(range(len(ref.gold))) - initial

    def align(graph):
        return ref.match(graph) - initial, goal

    return d, align


def run(a):
    for case in os.environ.get("COMP_EGG", "fact loopfact sum-divisors").split():
        d, align = egg(a, case)
        nets = {
            (arm, seed): network(a, arm, seed)
            for arm in os.environ.get("COMP_MODELS", "prior A B C").split()
            for seed in (71, 113)
        }
        w = World(d, next(iter(nets.values())).actor, entry_table=None, sides="")
        rows = []
        for block in range(int(os.environ.get("COMP_BLOCKS", "2"))):
            order = [
                (key, mode)
                for key in nets
                for mode in os.environ.get("COMP_DRAWS", "iid").split()
            ]
            if block % 2:
                order.reverse()
            for (arm, seed), mode in order:
                net = nets[arm, seed]
                net.static_cache.clear()
                policy = Policy(net, mode == "unique")
                res = native(a, w, seed=193, policy=policy, reference=align)
                rows.append(
                    dict(
                        case=case,
                        arm=arm,
                        seed=seed,
                        mode=mode,
                        block=block,
                        attempts=policy.slots,
                        **res,
                    )
                )
                store(d / ("results" + os.environ.get("COMP_TAG", "") + ".json"), rows)
                print(
                    case,
                    arm,
                    seed,
                    block,
                    res["covered"],
                    res["reference"],
                    round(res["wall"], 2),
                    flush=True,
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
