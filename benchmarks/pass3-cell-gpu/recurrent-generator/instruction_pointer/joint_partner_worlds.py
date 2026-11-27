"""Native marginal twins and nested same-type distractors. Gold only from replay."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random
import numpy as np
from binding_packets import packet
from binding_worlds import build
from binding_model import parser, read_packet
from completion_context import write

KINDS = ("one", "two", "three", "chain")
ARMS = ("independent", "cell", "tensor", "wide", "dense")
SIZES = (4, 8, 16, 32, 64, 128, 256, 512, 1024)


def world(i, n, kind, flip, held, counts=None, *, parity=False, near=False, partners=1):
    # Deterministic streams per semantic row; adding rows cannot alter earlier values.
    rng = random.Random(7927 * i)
    val = rng.sample(range(1 << 20), 80)
    offset = (i + 1) << 35
    names = ["v" + str(k) for k in rng.sample(range(90000), 12)]
    a, b, c, d, e, f, g = names[:7]
    width = {"one": 1, "two": 2, "three": 3, "chain": 2}[kind]
    x, y, z, u, v, w, h1, h2 = val[:8]
    left = [[x, y, z], [u, v, w]]
    right = [[x, y, z], [u, v, w]]
    if kind == "chain":
        right[0][2], right[1][2] = h1, h2
        tail = [[h2 if flip else h1, *val[20:22]], [*val[22:25]]]
    elif width == 1:
        right[flip][0] = val[12]
    else:
        # Root zero asks for the diagonal, root one for the off-diagonal.
        left[1] = left[0].copy()
        left[1][width - 1] = right[1][width - 1]
        if flip:
            right[0][width - 1], right[1][width - 1] = (
                right[1][width - 1],
                right[0][width - 1],
            )
    if parity:
        assert kind == "three"
        left = [[x, y, z], [x, y, w]]
        right = [
            [(x, u)[p], (y, v)[q], (z, w)[p ^ q ^ flip]] for p in (0, 1) for q in (0, 1)
        ]
    if partners != 1:
        if kind != "two" or not 1 < partners < n:
            raise ValueError("multiple distinct outputs require a two-field world")
        right.extend([*right[0][:2], 2**20 + j] for j in range(1, partners))
    result_field = d if partners != 1 else c
    schemas = [[a, b, c], [*[a, b, c][:width], *[d, e, f][: 3 - width]]]
    data = [left, right]
    if kind == "chain":
        schemas.append([d, e, g])
        data.append(tail)
    tables = ["Left", "Mid", "Tail"][: len(data)]
    program = ["(ruleset warm)", "(ruleset probe)", "(relation Result (i64 i64 i64))"]
    atoms = []
    for role, (rows, slots, table) in enumerate(
        zip(data, schemas, tables, strict=True)
    ):
        count = counts[role] if counts else n
        extra = random.Random(i * 701 + role)
        for j in range(len(rows), count):
            # Reserved disjoint namespaces exclude additional matches by construction.
            rows.append(
                [2**21 + role * 2**23 + j * 16 + q for q in extra.sample(range(16), 3)]
            )
            if near:
                if kind != "two":
                    raise ValueError("one-field near misses require the double-variable fixture")
                q = j % 2
                rows[-1][q] = (x, y)[q]
        perm = np.roll(np.arange(3), (role + i) % 3)
        if held and role == 1:
            perm = perm[::-1]
        program.append(f"(relation {table} (i64 i64 i64))")
        atoms.append("(" + table + " " + " ".join(slots[j] for j in perm) + ")")
        # Random order independent of flip and size; ties broken by row index.
        order = sorted(
            range(count),
            key=lambda j: random.Random(i * 12457 + j * 29 + role).random(),
        )
        for j in order:
            program.append(
                "("
                + table
                + " "
                + " ".join(str(offset + rows[j][q]) for q in perm)
                + ")"
            )
    program += [
        "(rule (" + " ".join(atoms) + f") ((Result {a} {b} {result_field})) :ruleset probe)",
        "(run-schedule (run warm) (run probe))",
    ]
    return "\n".join(program) + "\n"


def jobs():
    for n in (4, 8, 16, 32):
        for j, kind in enumerate(KINDS):
            for k in range(6):
                for flip in (0, 1):
                    yield "fit", 130000 + n * 1000 + k * 8 + j, n, kind, flip, False
    for n in SIZES:
        for j, kind in enumerate(KINDS):
            for k in range(6 if n <= 32 else 3):
                for flip in (0, 1):
                    yield "held", 300000 + k * 8 + j, n, kind, flip, True


def folder(a, job):
    split, i, n, k, p, _ = job
    return a.out / "worlds" / split / f"{n:04}-{k}-{i:05}-{p}"


def prepare(a):
    def compile_one(job):
        split, i, n, k, p, held = job
        build(a, (split, i, n, k, p, False, False), override=world(i, n, k, p, held))

    work = list(jobs())
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(compile_one, work))
    held_bindings = {}
    for job in work:
        d = folder(a, job)
        packet(a, d)
        z = read_packet(d / "binding.pkl")
        assert len(z["gold"]) == 1 and all(len(b["row"]) == job[2] for b in z["banks"])
        if job[0] == "held":
            values = tuple(
                tuple(b["raw"][i, :3])
                for b, i in zip(z["banks"], z["gold"][0], strict=True)
            )
            key = (job[1], job[3], job[4])
            assert held_bindings.setdefault(key, values) == values, (
                job,
                "changed binding",
            )
        if job[3] in ("two", "three") and job[4]:
            other = read_packet(folder(a, (*job[:4], 0, job[-1])) / "binding.pkl")
            for side in (0, 1):
                A, B = [s["banks"][side]["raw"] for s in (z, other)]
                assert np.array_equal(np.sort(A, axis=0), np.sort(B, axis=0)), (
                    job,
                    side,
                )
            roots = [
                tuple(s["banks"][0]["raw"][s["gold"][0][0], :3]) for s in (z, other)
            ]
            assert roots[0] != roots[1]
    write(
        a.out / "manifest.json",
        dict(
            fit=sum(j[0] == "fit" for j in work),
            held=sum(j[0] == "held" for j in work),
            targets=len(work),
        ),
    )


def options():
    p = parser()
    p.add_argument(
        "task", choices=["prepare", "train", "evaluate", "live", "cost", "cpu"]
    )
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--previous-binding", type=Path, required=True)
    p.add_argument("--previous-first", type=Path, required=True)
    return p


if __name__ == "__main__":
    import torch

    torch.set_num_threads(1)
    a = options().parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    prepare(a)
