"""Prepare upstream egglog controls and larger inputs with the same join rules."""

import argparse
import json
import os
import re
import signal
import subprocess
from pathlib import Path


def cyk_input(tests):
    src = (tests / "cykjson.egg").read_text()

    def inline(m):
        relation, filename = m.groups()
        lines = []
        for line in (tests / filename).read_text().splitlines():
            values = line.split("\t")
            if relation == "getString":
                pos, word = values
                lines.append(f"(set (getString {int(pos)}) {json.dumps(word)})")
            else:
                lines.append(
                    "(" + relation + " " + " ".join(map(json.dumps, values)) + ")"
                )
        return "\n".join(lines)

    return re.sub(
        r'^\(input (\S+) "\./tests/([^"]+)"\)$', inline, src, flags=re.MULTILINE
    )


def workloads(tests):
    for name in (
        "points-to",
        "eqsat-basic",
        "path",
        "cyk",
        "matrix",
        "unification-points-to",
    ):
        yield name, tests / "web-demo" / (name + ".egg"), None
    for name in (
        "math-microbenchmark",
        "fibonacci-demand",
        "cykjson",
        "eggcc-extraction",
        "hardboiled_conv1d_32",
    ):
        yield name, tests / (name + ".egg"), None
    yield "cykjson-inline", tests / "cykjson.egg", cyk_input(tests)
    yield (
        "cykjson-rows",
        tests / "cykjson.egg",
        cyk_input(tests).replace(
            '(let $test1 (B 801 1 "VAL"))',
            "; unused post-run binding removed for lowering",
        ),
    )
    source = tests / "web-demo/path.egg"
    rules = source.read_text().split("(edge 1 2)")[0]
    n = 160
    edges = [f"(edge {i} {i + 1})" for i in range(n)]
    yield (
        "path-chain160",
        source,
        rules + "\n".join(edges) + f"\n(run {n + 1})\n(check (path 0 {n}))\n",
    )
    source = tests / "web-demo/points-to.egg"
    src = source.read_text()
    facts = []
    for i in range(256):
        facts.extend(
            [
                f'(New "o{i}a" $A)',
                f'(New "o{i}b" $B)',
                f'(Assign "o{i}c" "o{i}b")',
                f'(Store "o{i}b" $f "o{i}a")',
                f'(Load "r{i}" "o{i}c" $f)',
            ]
        )
    yield (
        "points-to-256",
        source,
        src.replace("(run 3)", "\n".join(facts) + "\n(run 100)"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("compiler", type=Path)
    p.add_argument("tests", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--only", nargs="+")
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    for name, source, derived in workloads(a.tests.resolve()):
        if a.only and name not in a.only:
            continue
        dest = a.out / name
        if (dest / "program.json").exists():
            continue
        if derived is not None:
            source = a.out / (name + ".egg")
            source.write_text(derived)
        with (a.out / (name + ".log")).open("w") as log:
            extra = []
            if name == "path-chain160":
                donor = a.out / "path-donor.egg"
                donor.write_text(
                    derived.split("(edge 0 1)")[0] + "(edge 0 1)\n(edge 1 2)\n(run 3)\n"
                )
                extra = ["--bake-source", donor.resolve()]
            command = [
                a.compiler.resolve(),
                "compile",
                "--source",
                source.resolve(),
                "--output",
                dest.resolve(),
                *extra,
            ]
            with subprocess.Popen(
                command,
                cwd=a.tests.resolve().parent,
                stderr=subprocess.STDOUT,
                stdout=log,
                start_new_session=True,
            ) as proc:
                try:
                    code = proc.wait(timeout=25)
                    if code:
                        log.write(f"\ncompiler exited {code}\n")
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    log.write("\n25 second compilation budget exhausted\n")
