"""Build real native environments and verify the complete next-Cell set offline."""

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path

import torch

from address_scores import weight
from coverage_examples import pack
from discrete_cells import from_q
from discovery_states import cli
from next_cell_corpus import store_file
from query_environment import conditioned

SIZES = (4, 8, 16, 32, 64, 128, 256, 1024)
VARIANTS = (
    "pair",
    "typed-noise",
    "rules2",
    "rules4",
    "unary",
    "triple",
    "many",
    "prefix",
)


def environment(n, variant, instance, permutation):
    # An instance fixes semantic values independently of size and physical order.
    values = random.Random(40703 + instance).sample(range(1, 2000000), 4096)
    arity = {"unary": 1, "triple": 3}.get(variant, 2)
    rules = {"rules2": 2, "rules4": 4}.get(variant, 1)
    warm = min(1 + instance % 3, n // 4) if variant == "prefix" else 0
    edge_count = n - warm
    copies = max(1, min(32, n // 4)) if variant == "many" else 1
    rows = []
    # Same increasing chain, including for the unary control.
    length = max(2, arity)
    for job in range(copies):
        v = sorted(values[job * 4 : job * 4 + length + 1])
        rows.extend(("Edge", x, y) for x, y in zip(v, v[1:]))
    # A joinable decreasing chain satisfies the shared variable and fails the guard.
    noise = "Noise" if variant == "typed-noise" else "Edge"
    for j in range(2):
        if len(rows) < edge_count:
            v = sorted(values[256:259], reverse=True)
            rows.append((noise, v[j], v[j + 1]))
    i = 512
    while len(rows) < edge_count:
        x, y = sorted(values[i : i + 2], reverse=True)
        rows.append((noise, x, y))
        i += 2
    # Seed witnesses remain visible after publication, so budget counts them too.
    if warm:
        # Any k of these 2k producers can enable a different legal continuation.
        start, mid = sorted(values[:2])
        rows[0] = ("Edge", start, mid)
        for j in range(2 * warm):
            rows[1 + j] = ("Seed", mid, 2000001 + values[300 + j])

    random.Random(991 * permutation + instance + 172).shuffle(rows)
    body = [
        "(relation Edge (i64 i64))",
        "(relation Noise (i64 i64))",
        "(relation Seed (i64 i64))",
        "(ruleset build)",
        "(ruleset probe)",
        "(rule ((Seed x y)) ((Edge x y)) :ruleset build)",
    ]
    variables = ["a", "b", "c", "d"][: arity + 1]
    atoms = " ".join(f"(Edge {x} {y})" for x, y in zip(variables, variables[1:]))
    last = variables[-1]
    guards = [f"(< a {last})", f"(< {last} a)", "(< b a)", "(< a b)"]
    for r in range(rules):
        body.extend(
            [
                f"(relation Result{r} (i64 i64))",
                f"(rule ({atoms} {guards[r]}) ((Result{r} a {last})) :ruleset probe)",
            ]
        )
    body.extend(f"({t} {x} {y})" for t, x, y in rows)
    body.append("(run-schedule (run build) (run probe))")
    return "\n".join(body) + "\n", rows


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, separators=(",", ":")) + "\n")


def cmd(args, env=None):
    result = subprocess.run(args, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError(result.stderr.decode()[-2000:])
    return result.stdout


def native(a, d, mode, tape, *args, env=None):
    return json.loads(
        cmd(
            [
                a.runtime_binary,
                mode,
                d / "program.json",
                tape,
                "audit",
                *map(str, args),
            ],
            env,
        )
    )


def directory(a, n, v, i, p):
    return a.out / "worlds" / f"{n:04}-{v}-{i:03}-{p}"


def frames(a, d):
    return conditioned(a, d, d / "observer.jsonl")


@torch.no_grad()
def build(a, n, v, i, p, gate, *, output=None, name_order=None):
    d = directory(a, n, v, i, p) if output is None else output
    d.mkdir(parents=True, exist_ok=True)
    text, rows = environment(n, v, i, p)
    src = d / "world.egg"
    src.write_text(text)
    from tempfile import TemporaryDirectory
    from shutil import copyfile

    with TemporaryDirectory() as tmp:
        output = Path(tmp) / "ir"
        cmd([a.compiler, "compile", "--source", src, "--output", output])
        copyfile(output / "program.json", d / "program.json")
    name_order = p if name_order is None else name_order
    address_seed = (
        None if a.canonical_names else 73831 + 257 * i + 67108859 * name_order
    )
    native(
        a,
        d,
        "capture",
        d / "teacher.json",
        "--memory",
        d / "teacher-frames.jsonl",
        "--ept-origins",
        *(("--address-seed", address_seed) if address_seed is not None else ()),
    )
    tape = read(d / "teacher.json")
    warm = [q for q in tape["requests"] if q["run"] == 1]
    # Shuffle legal warm requests and rename their request IDs before replay.
    if warm:
        first = json.loads((d / "teacher-frames.jsonl").open().readline())
        fields = {(k["token"], k["op"]): v["hashes"] for k, v in first["updates"]}
        warm.sort(
            key=lambda q: fields[
                (q["parents"][0]["address"]["token"], q["parents"][0]["address"]["op"])
            ]
        )
        warm = random.Random(39119 + i).sample(warm, len(warm) // 2)
    rng = random.Random(917 * p + i)
    rng.shuffle(warm)
    for q, uid in zip(warm, rng.sample(range(10000, 100000), len(warm))):
        q["token"] = uid
    write(d / "prefix.json", dict(tape, requests=warm))
    fresh = native(a, d, "replay", d / "prefix.json", 1, "--audit-next-proofs")
    for j, q in enumerate(fresh):
        q["token"] = 100001 + j
    write(d / "verified.json", dict(tape, requests=warm + fresh))
    rep = native(
        a,
        d,
        "replay",
        d / "verified.json",
        2,
        "--memory",
        d / "frames.jsonl",
        "--ept-origins",
        env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(d / "observer.jsonl")),
    )
    origins = dict(rep["ept"]["origins"])
    if (
        rep["counts"]["accepted"] != len(warm) + len(fresh)
        or not fresh
        or any(origins.get(q["token"], 0) != 1 for q in fresh)
    ):
        raise ValueError(f"invalid positive set at {d}: {rep['counts']}, {len(fresh)}")
    cells = [from_q(q) for q in fresh]
    m = frames(a, d)
    try:
        for line in (d / "frames.jsonl").open():
            f = json.loads(line)
            m.update(f)
            if f["run"] == 2:
                break
        live = {
            addr: row for addr, (row, _) in m.pub.live.items() if not row["forwarded"]
        }
        if (
            len(live) != n
            or len({owner for owner, _ in live}) != n
            or len(m.pub.live) != n
            or len(cells) != len(set(cells))
        ):
            raise ValueError(
                f"visible owners/rows {len(live)}/{len(m.pub.live)} expected {n} in {d}"
            )
        block = pack(m, cells, gate, "context", 2)
        info = dict(
            address_seed=address_seed,
            size=n,
            variant=v,
            instance=i,
            permutation=p,
            targets=len(cells),
            rules=len(m.ids),
            arity=len(cells[0].refs),
            domain_sizes=[len(m.rows[t]) for t in m.roles[cells[0].rule]],
            warm=len(warm),
            positive_versions=sum(row["version"] > 0 for row in live.values()),
            hash=hashlib.sha256(text.encode()).hexdigest(),
            map_digest=hashlib.sha256(
                json.dumps(
                    sorted((addr, row["hashes"]) for addr, row in live.items())
                ).encode()
            ).hexdigest(),
        )
        write(d / "world.json", info)
        store_file(d / "packet.pkl.gz", block)
    finally:
        m.close_observer()


if __name__ == "__main__":
    parser = cli()
    parser.add_argument("--canonical-names", action="store_true")
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=SIZES)
    parser.add_argument(
        "--instances", type=int, nargs="+", default=[*range(12), 80, 81]
    )
    parser.add_argument("--variants", nargs="+", default=VARIANTS)
    a = parser.parse_args()
    torch.set_num_threads(1)
    gate = weight(a).to("mps").eval()
    for n in a.sizes:
        for v in a.variants:
            for i in a.instances:
                for p in (0, 1) if i >= 80 else (i % 2,):
                    build(a, n, v, i, p, gate)
        print(n, "verified", flush=True)
