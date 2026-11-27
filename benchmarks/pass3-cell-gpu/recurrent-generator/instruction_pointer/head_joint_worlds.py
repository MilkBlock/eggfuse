"""Fresh native worlds for size and distractor-density extrapolation."""

from copy import copy

from binding_packets import packet
from binding_worlds import build
from joint_partner_worlds import world
from partner_index_worlds import args, folder


def suite(a):
    previous = copy(a)
    previous.out = a.selective.parent / "partner-index"
    for n in (1024, 8192, 32768, 131072):
        for valid in (1, 8):
            for flip in (0, 1):
                i = 511000
                mode = "multi" if valid == 8 else "hard"
                if n < 131072:
                    d = folder(previous, (mode, n, i, flip))
                else:
                    d = a.out / "worlds" / mode / f"{n}-two-{i}-{flip}"
                yield n, valid, flip, 1.0, i, d
    for density in (0.0, 0.5):
        for flip in (0, 1):
            yield (
                32768,
                1,
                flip,
                density,
                511000,
                a.out / "worlds" / f"near{density}" / f"32768-two-511000-{flip}",
            )


if __name__ == "__main__":
    import torch

    torch.set_num_threads(1)
    a = args()
    for n, valid, flip, density, i, d in suite(a):
        if not (d / "ok.json").exists():
            build(
                a,
                (d.parent.name, i, n, "two", flip, False, False),
                override=world(
                    i,
                    n,
                    "two",
                    flip,
                    True,
                    near=True,
                    partners=valid,
                    near_fraction=density,
                ),
            )
        packet(a, d)
        print(d.name, valid, density, flush=True)
