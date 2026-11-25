"""Compile bounded critical-path computations and wire native named receipts without reading proof tapes."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from time import perf_counter

from recursive_train import binary, folder, read


def dependencies(shape, size, arity):
    result = [tuple(range(-arity, 0))]
    for i in range(1, size):
        if shape == "line" or i % 3 == 1 or i == size - 1 and i % 3 == 2:
            src = (i - 1,)
        elif i % 3 == 2:
            src = (i - 2,)
        else:
            src = (i - 2, i - 1)
        result.append(src)
    return result


def graph_program(shape, size, arity, offset, jobs=1):
    deps = dependencies(shape, size, arity)

    def table(i):
        return f"Start{-i}" if i < 0 else f"Finish{i}"

    facts = {
        (table(i), job): offset + 3 * -i + job * (1 - i) for i in range(-arity, 0) for job in range(jobs)
    }
    typed = "i64 i64" if jobs > 1 else "i64"
    key = "job " if jobs > 1 else ""
    lines = [f"(relation {table(i)} ({typed}))" for i in range(-arity, size)]
    for i, src in enumerate(deps):
        args = [f"x{j}" for j in range(len(src))]
        start = args[0]
        for arg in args[1:]:
            start = f"(max {start} {arg})"
        duration = 1 + (7 * i + 3) % 13
        for job in range(jobs):
            facts[table(i), job] = max(facts[table(j), job] for j in src) + duration
        conditions = " ".join(f"({table(j)} {key}{v})" for j, v in zip(src, args, strict=True))
        lines.extend(
            [
                f"(ruleset s{i})",
                f"(rule ({conditions}) (({table(i)} {key}(+ {start} {duration}))) :ruleset s{i})",
            ]
        )
    for i in range(-arity, 0):
        for job in range(jobs):
            prefix = f"{job} " if jobs > 1 else ""
            lines.append(f"({table(i)} {prefix}{facts[table(i), job]})")
    lines.append("(run-schedule " + " ".join(f"(run s{i})" for i in [*range(size), size - 1]) + ")")
    return "\n".join(lines) + "\n", facts


def module(steps, recursive=False):
    """Each child imports table names and exports unique named producer positions in this circuit."""

    def leaf(step):
        rid, inputs, outputs = step
        return (
            inputs,
            [(rid, 0, [(-1, j) for j in range(len(inputs))])],
            {tab: (0, pc) for pc, tab in outputs.items()},
        )

    def compose(left, right):
        ports, seq, exports = left
        inputs, body, results = right
        ports = list(ports)
        mapping = []
        for t in inputs:
            if t in exports:
                mapping.append(exports[t])
            else:
                if t not in ports:
                    ports.append(t)
                mapping.append((-1, ports.index(t)))
        offset = len(seq)
        tail = [
            (rid, offset + i, [mapping[pc] if owner < 0 else (offset + owner, pc) for owner, pc in wires])
            for i, (rid, _, wires) in enumerate(body)
        ]
        if exports.keys() & results.keys():
            raise ValueError("ambiguous named producer in critical-path program")
        return ports, seq + tail, {**exports, **{t: (offset + i, pc) for t, (i, pc) in results.items()}}

    level = [leaf(step) for step in steps]
    if recursive:
        while len(level) > 1:
            level = [
                compose(*level[i : i + 2]) if i + 1 < len(level) else level[i]
                for i in range(0, len(level), 2)
            ]
        return level[0]
    result = level[0]
    for item in level[1:]:
        result = compose(result, item)
    return result


def recursive_named(unit):
    """Link contiguous subprograms by their named imports, keeping distinct same-type boundaries."""

    def link(lo, hi):
        if hi == lo + 1:
            rid, stage, inputs = unit[lo]
            ports = list(dict.fromkeys(map(tuple, inputs)))
            body = [(rid, stage, [(-1, ports.index(tuple(ref))) for ref in inputs])]
            return ports, body
        mid = (lo + hi) // 2
        ports, left = link(lo, mid)
        imports, right = link(mid, hi)
        mapping = []
        for owner, pc in imports:
            if lo <= owner < mid:
                mapping.append((owner - lo, pc))
            else:
                ref = owner, pc
                if ref not in ports:
                    ports.append(ref)
                mapping.append((-1, ports.index(ref)))
        tail = [
            (rid, stage, [mapping[pc] if owner < 0 else (owner + mid - lo, pc) for owner, pc in wires])
            for rid, stage, wires in right
        ]
        return ports, left + tail

    ports, body = link(0, len(unit))
    return [
        (rid, stage, [ports[pc] if owner < 0 else (owner, pc) for owner, pc in wires])
        for rid, stage, wires in body
    ]


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def prepare(root, compiler, out, shape, size, arity, offset, jobs=1):
    name = f"scale-{shape}-{size}-{arity}-{offset}"
    if jobs > 1:
        name += f"-jobs{jobs}"
    d = folder(root, name)
    d.mkdir(parents=True, exist_ok=True)
    text, expected = graph_program(shape, size, arity, offset, jobs)
    egg = d.with_suffix(".egg")
    egg.write_text(text)
    tick = perf_counter()
    with TemporaryDirectory(dir=out) as tmp:
        dest = Path(tmp) / "compiled"
        subprocess.run(
            [compiler, "compile", "--source", egg, "--output", dest], stdout=subprocess.DEVNULL, check=True
        )
        copyfile(dest / "program.json", d / "program.json")
    compile_seconds = perf_counter() - tick
    program = d / "program.json"
    contract = json.loads(subprocess.check_output([binary(root), "receipt-contract", program]))
    steps = [
        (i, [a["table"] for a in r["inputs"]], {int(pc): v["table"] for pc, v in r["outputs"].items()})
        for i, r in enumerate(contract["rules"])
    ]
    tables = [t["name"] for t in read(program)["recipe"]["tables"]]
    steps.sort(
        key=lambda step: int(next(tables[t] for t in step[2].values() if tables[t].startswith("Finish"))[6:])
    )
    tick = perf_counter()
    ports, unit, _ = module(steps)
    flat_seconds = perf_counter() - tick
    tick = perf_counter()
    alternate = module(steps, True)
    nested_seconds = perf_counter() - tick
    if unit != alternate[1] or ports != alternate[0] or len(ports) != arity or len(unit) != size:
        raise ValueError("lowered interfaces disagree")
    save(d / "layouts.json", [unit])
    cap = subprocess.check_output(
        [
            binary(root),
            "capture",
            program,
            d / "tape.json",
            "audit",
            "--export",
            d / "reference-state.json",
            "--ept",
        ]
    )
    (d / "capture.json").write_bytes(cap)
    actual = {
        (row["table"], row["values"][0]["value"] if jobs > 1 else 0): row["values"][int(jobs > 1)]["value"]
        for row in read(d / "reference-state.json")["rows"]
        if not row["subsumed"]
    }
    if expected != actual or len(read(d / "tape.json")["requests"]) != size * jobs:
        raise ValueError("native critical-path results differ from independent recurrence")
    save(
        out / (name + ".json"),
        dict(
            case=name,
            size=size,
            arity=arity,
            shape=shape,
            offset=offset,
            jobs=jobs,
            compile_seconds=compile_seconds,
            flat_compose_seconds=flat_seconds,
            recursive_compose_seconds=nested_seconds,
            source_sha=hashlib.sha256(text.encode()).hexdigest(),
            terminal=read(d / "capture.json")["state_sha"],
            graph_signature=hashlib.sha256(json.dumps(unit).encode()).hexdigest(),
            ports=ports,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "compiler", "out"):
        p.add_argument(name, type=Path)
    p.add_argument("--sizes", nargs="+", type=int, default=[6, 16, 32, 64, 128, 256, 512])
    p.add_argument("--jobs", type=int, default=1)
    args = p.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    if args.jobs > 1:
        for arity in (1, 2, 4):
            prepare(args.root, args.compiler, args.out, "fork", 32, arity, 17, args.jobs)
        raise SystemExit(0)
    for n in args.sizes:
        for shape in ("fork", "line"):
            for a, v in [(1, 17), (2, 17), (4, 17), (1, 73)] if n == 32 and shape == "fork" else [(1, 17)]:
                prepare(args.root, args.compiler, args.out, shape, n, a, v)
                print(shape, n, a, v, flush=True)
