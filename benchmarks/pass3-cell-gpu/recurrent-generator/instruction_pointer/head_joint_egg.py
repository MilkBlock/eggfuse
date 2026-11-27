"""Dynamic multi-rule transfer using the existing frozen neural template sampler."""

import torch

import head_joint_index as joint
import partner_index as old
from binding_egg import execute
from binding_model import collate
from completion_context import read
from first_parent import records
from partner_index_worlds import args, frozen
from recursive_coverage import Target, snapshot
from recursive_train import folder
from selective_kernel import pack


def parent_policy(model, arm):
    def bind(z, paired, rng, stats):
        z = dict(z, banks=[dict(b, last=-1) for b in z["banks"]])
        arity = len(z["banks"])
        slots = paired.size(1)
        try:
            data = pack([z]) if arity >= 2 else None
        except ValueError as exc:
            if str(exc) != "requires exactly one earlier connected role per child":
                raise
            data = None
        if data is None:
            stats["fallback_slots"] += slots
            return model.local.base(collate([z]), noise=paired, draws=slots)[1]
        stats["index_pages"] += 1
        stats["index_slots"] += slots
        stats[f"arity_{arity}_slots"] += slots
        stats["partner_rows_indexed"] += sum(len(v) for v in z["addrs"][1:])
        u = old.noise(rng, slots, arity)
        u[:, :, :, 0, 0] = paired
        if arm == "joint":
            return joint.draw(data, joint.prepare(model, data), u)
        return old.draw(model, data, old.prepare(model, data), u, "shared-score")[0]

    return bind


@torch.no_grad()
def run(a):
    rows = []
    a.slots = 8
    seed = a.seeds[0]
    model = frozen(a, seed)
    for case in ("fact", "loopfact", "sum-divisors"):
        d = folder(a.data, case)
        root = a.out / "egg" / case
        root.mkdir(parents=True, exist_ok=True)
        ref = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, root / "reference.json")[0],
        )
        init = ref.match(
            snapshot(a.data, d, "reference", "-", 0, root / "initial.json")[0]
        )
        for block in range(4):
            for arm in (
                ("shared-score", "joint") if block % 2 == 0 else ("joint", "shared-score")
            ):
                dest = root / f"{arm}-{block}"
                execute(
                    a,
                    d,
                    dest,
                    model.local.base,
                    arm,
                    seed,
                    block,
                    seed + 101,
                    (ref, init),
                    parent_policy=parent_policy(model, arm),
                    address_seed=170003 + seed,
                )
                r = read(dest / "result.json")
                s = r["stats"]
                rows.append(
                    {
                        "case": case,
                        "arm": arm,
                        "block": block,
                        "paid": s["paid"],
                        "ops": r["ops"],
                        "coverage": r["covered"] / r["reference"],
                        "covered": r["covered"],
                        "reference": r["reference"],
                        "ept": r["ept"],
                        "eps": r["eps"],
                        "wall": r["wall"],
                        "graph": r["graph"],
                        "pages": s.get("index_pages", 0),
                        "slots": s.get("index_slots", 0),
                        "three_plus": sum(
                            v
                            for k, v in s.items()
                            if k.startswith("arity_") and int(k.split("_")[1]) >= 3
                        ),
                        "partner_rows": s.get("partner_rows_indexed", 0),
                        "attempts": s["attempts"],
                    }
                )
                records(a.out / "egg.csv", rows)
                print(case, arm, block, rows[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
