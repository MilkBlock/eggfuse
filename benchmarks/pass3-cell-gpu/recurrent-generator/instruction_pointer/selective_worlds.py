"""Native type-domain interventions. All supervision is resolved in a separate named replay."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import torch
from binding_packets import packet
from binding_model import read_packet
from binding_worlds import build
from joint_partner_worlds import world, options

SIZES = (32, 128, 256, 1024, 4096, 8192)


def args():
    p = options()
    p.add_argument(
        "--near", action="store_true", help="run the one-field near-miss online control"
    )
    p.add_argument("--previous-joint", required=True, type=Path)
    return p.parse_args()


def cases():
    for n in SIZES:
        for side in ("square", "left", "right"):
            if n == 32 and side != "square":
                continue
            for k in (0, 1):
                for flip in (0, 1):
                    yield side, n, "two", 300001 + 8 * k, flip
    for n in (32, 256, 1024, 4096):
        for kind in ("chain", "fork"):
            for flip in (0, 1):
                yield "square", n, kind, 390001, flip


def path(a, case):
    side, n, k, i, f = case
    if k == "two" and n <= 1024 and side == "square":
        base = a.previous_joint / "worlds/held"
    else:
        base = a.out / "worlds" / side
    return base / f"{n:04}-{k}-{i:05}-{f}"


def fork(i, n, flip):
    rng = random.Random(i)
    base = i << 35
    x, y, u, v = rng.sample(range(1, 65536), 4)
    sets = [
        [(x, y, 1), (x, v, 2), (u, y, 3), (u, v, 4)],
        [(x, 4, 5)],
        [(v if flip else y, 7, 8)],
    ]
    lines = ["(ruleset warm)", "(ruleset probe)", "(relation Result (i64 i64 i64))"]
    for h, (table, rows) in enumerate(zip(("Left", "Mid", "Tail"), sets)):
        rows.extend(
            tuple((h + 1) * 2**23 + j * 8 + c for c in (0, 1, 2))
            for j in range(len(rows), n)
        )
        rng.shuffle(rows)
        lines.append(f"(relation {table} (i64 i64 i64))")
        lines += [
            "(" + table + " " + " ".join(str(base + t) for t in r) + ")" for r in rows
        ]
    return (
        "\n".join(
            lines
            + [
                "(rule ((Left a b c) (Mid a m d) (Tail b e f)) ((Result a b c)) :ruleset probe)",
                "(run-schedule (run warm) (run probe))",
            ]
        )
        + "\n"
    )


def prepare(a):
    def one(case):
        side, n, k, i, f = case
        if (path(a, case) / "ok.json").exists():
            return
        counts = {"square": (n, n, n), "left": (n, 32), "right": (32, n)}[side]
        src = fork(i, n, f) if k == "fork" else world(i, n, k, f, True, counts)
        build(a, (side, i, n, k, f, False, False), override=src)

    work = list(cases())
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, work))
    seen = {}
    for c in work:
        d = path(a, c)
        packet(a, d)
        z = read_packet(d / "binding.pkl")
        (gold,) = z["gold"]
        identity = tuple(tuple(b["raw"][j, :3]) for b, j in zip(z["banks"], gold))
        assert seen.setdefault(c[2:], identity) == identity, c
    print("verified", len(work), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
