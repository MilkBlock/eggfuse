"""Native held-out environments and randomized public address bindings."""

from concurrent.futures import ThreadPoolExecutor
from copy import copy
from pathlib import Path
import torch
from binding_packets import packet
from binding_worlds import build
from binding_model import read_packet
from joint_partner_worlds import options, world
from selective_kernel import net


def args():
    p = options()
    p.add_argument("--previous-joint", type=Path, required=True)
    p.add_argument("--selective", type=Path, required=True)
    return p.parse_args()


def frozen(a, seed):
    prev = copy(a)
    prev.out = a.selective
    return net(prev, seed, "mixed-sparse")


def cases():
    for n in (1024, 8192, 32768):
        for mode in ("hard", "multi"):
            for k in range((12 if n == 8192 else 4) if mode == "hard" else 2):
                for f in (0, 1):
                    yield mode, n, 511000 + k, f


def folder(a, case):
    mode, n, i, f = case
    base = (
        a.selective / "worlds/fresh-near"
        if mode == "hard" and n == 8192
        else a.out / "worlds" / mode
    )
    return base / f"{n:04}-two-{i:05}-{f}"


def prepare(a):
    def one(c):
        mode, n, i, f = c
        if not (folder(a, c) / "ok.json").exists():
            build(
                a,
                (mode, i, n, "two", f, False, False),
                override=world(
                    i,
                    n,
                    "two",
                    f,
                    True,
                    near=True,
                    partners=8 if mode == "multi" else 1,
                ),
            )

    work = list(cases())
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one, work))
    seen = {}
    for c in work:
        d = folder(a, c)
        packet(a, d)
        z = read_packet(d / "binding.pkl")
        g = z["gold"]
        assert len(g) == (8 if c[0] == "multi" else 1) and len({r[0] for r in g}) == 1
        labels = frozenset(
            tuple(tuple(b["raw"][j, :3]) for b, j in zip(z["banks"], refs))
            for refs in g
        )
        assert seen.setdefault((c[0], *c[2:]), labels) == labels
    print("verified", len(work), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
