"""Matched eight-slot independent executions and a separate receipt audit."""

import os

import torch

from binding_egg import execute
from completion_context import read
from head_joint_egg import parent_policy
from partner_index_worlds import args, frozen
from recursive_coverage import Target, snapshot
from recursive_train import folder


def random_template(net, m, program, u):
    ids = [r for r, h in m.ids if not h]
    return [ids[int(p * len(ids))] for p in u[:, 0]]


def random_bind(z, paired, rng, stats):
    sizes = paired.new_tensor([len(rows) for rows in z["addrs"]])
    return torch.minimum((paired * sizes).long(), sizes.long() - 1)


@torch.no_grad()
def run(a):
    a.slots = int(os.environ.get("MULTI_SLOTS", "8"))
    shift = int(os.environ.get("MULTI_DRAW_SHIFT", "0"))
    seed = a.seeds[0]
    for case in ("sum-divisors", "fact", "loopfact"):
        limit = (
            {"fact": 541, "loopfact": 745, "sum-divisors": 742}[case]
            if os.environ.get("MULTI_MATCH_PAID") == "1"
            else None
        )
        d = folder(a.data, case)
        root = a.out / case
        root.mkdir(parents=True, exist_ok=True)
        target = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, root / "ref.json")[0],
        )
        ref = (
            target,
            target.match(
                snapshot(a.data, d, "reference", "-", 0, root / "init.json")[0]
            ),
        )
        arms = os.environ.get("MULTI_ARMS", "audit,random").split(",")
        for block in range(int(os.environ.get("MULTI_BLOCKS", "1"))):
            for arm in arms if block % 2 == 0 else reversed(arms):
                model = frozen(a, seed)
                template = None
                bind = parent_policy(model, "joint")
                if arm == "random":
                    template = random_template
                    bind = random_bind
                elif arm == "flat-frozen":
                    from multirule_support import chooser

                    template = chooser(model, "ce-base")
                elif arm.startswith("ce-"):
                    from multirule_support import chooser

                    model.load_state_dict(
                        torch.load(a.out / f"{case}-{arm}.pt", weights_only=True)
                    )
                    template = chooser(model, arm)
                elif arm not in ("audit", "frozen"):
                    raise ValueError(arm)
                dest = root / (
                    f"{arm}-{block}"
                    if shift == 0 and a.slots == 8
                    else f"budget{a.slots}-draw{shift}-{arm}-{block}"
                )
                if limit is not None:
                    dest = dest.with_name("cap-" + dest.name)
                execute(
                    a,
                    d,
                    dest,
                    model.local.base,
                    arm,
                    seed,
                    block,
                    seed + 101 + shift,
                    ref,
                    parent_policy=bind,
                    address_seed=170003 + seed + shift,
                    template_policy=template,
                    audit_slots=arm == "audit",
                    paid_limit=limit,
                )
                r = read(dest / "result.json")
                print(
                    case,
                    arm,
                    block,
                    r["covered"],
                    r["stats"]["paid"],
                    r["receipts"],
                    flush=True,
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
