"""Freeze train/dev/blind CYK programs before training; capture native named proofs."""

import argparse
import hashlib
import json
import random
import shutil
import subprocess
from pathlib import Path


def grammar(seed):
    rng = random.Random(seed)
    n = rng.randint(7, 14)
    productions = set()
    ends = set()
    words = []
    for i in range(n):
        word = rng.randrange(5)
        ends.add((f"N{i}", f"w{word}"))
        words.append(f"w{word}")
    frontier = list(range(n))
    while len(frontier) > 1:
        i = rng.randrange(len(frontier) - 1)
        productions.add((f"N{n}", f"N{frontier[i]}", f"N{frontier[i + 1]}"))
        frontier[i : i + 2] = [n]
        n += 1
    # Extra parents are higher than either child, preserving finite trees.
    for _ in range(n):
        parent = rng.randrange(2, n)
        productions.add(
            (f"D{_}", f"N{rng.randrange(parent)}", f"N{rng.randrange(parent)}")
        )
    init = ['(Prod "{}" "{}" "{}")'.format(*q) for q in sorted(productions)]
    init += ['(End "{}" "{}")'.format(*q) for q in sorted(ends)]
    init += [f'(set (getString {i}) "{w}")' for i, w in enumerate(words, 1)]
    return "\n".join(init) + "\n(run 10000)\n"


def main(root, out, extra_blind=(), cases=None):
    tree = root / "model-tree"
    src = (tree / "egglog/tests/cykjson.egg").read_text().split("(input Prod")[0]
    # These seed groups are disjoint. No blind capture is used for fitting.
    split = {
        "train": [17118, 17119, 17120, 17121],
        "validation": [17122],
        "blind": [91627433, 72102993, *extra_blind],
    }
    out.mkdir(exist_ok=True, parents=True)
    if cases is None or not (out / "split.json").exists():
        (out / "split.json").write_text(json.dumps(split, indent=2))
    compiler = root / "unified-scale/build/release/eggfuse-cell-compiler"
    binary = root / "unified-scale/build/release/examples/cell_token_replay"
    sources = {
        f"grammar-{s}": src + grammar(s) for seeds in split.values() for s in seeds
    }
    if cases and any(name.startswith("grammar-stride") for name in cases):
        from txn_chain_corpus import chain_sources

        sources.update(chain_sources(src))
    # Hold out a rule layout as well as its input. Materialize a redundant
    # four-column production certificate, preserving the reference parse.
    template_case = "grammar-layout-832749"
    payload = grammar(832749)
    certificate = src.replace(
        "(relation Prod",
        "(relation Allowed (String String String String))\n(relation Prod",
    )
    assert certificate.count("((Prod a b c)") == 2
    certificate = certificate.replace(
        "((Prod a b c)", "((Allowed a b c a) (Prod a b c)"
    )
    allowed = []
    for line in payload.splitlines():
        if line.startswith("(Prod "):
            _, a, b, c = line[1:-1].split()
            allowed.append(f"(Allowed {a} {b} {c} {a})")
    sources[template_case] = certificate + "\n".join(allowed) + "\n" + payload
    sources["cyk801"] = (
        (root / "oracle-survey/cykjson-rows.egg")
        .read_text()
        .replace('(check (P 801 1 "VAL"))', "")
    )
    names = [*sources, "jacobi"] if cases is None else cases
    for name in names:
        if name not in sources and name != "jacobi":
            raise ValueError(f"unknown corpus case: {name}")
        d = out / name
        if (d / "capture.json").exists():
            continue
        if name in sources:
            source = out / (name + ".egg")
            source.write_text(sources[name])
            if not (d / "program.json").exists():
                subprocess.run(
                    [compiler, "compile", "--source", source, "--output", d],
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
        else:
            d.mkdir(exist_ok=True)
            shutil.copyfile(
                root.parent
                / "frozen-native-plans-parity-v2/jacobi-1d/rust-1703/program.json",
                d / "program.json",
            )
        cmd = [
            binary,
            "capture",
            d / "program.json",
            d / "tape.json",
            "audit",
            "--memory",
            d / "memory.jsonl",
            "--ept",
        ]
        capture = json.loads(subprocess.check_output(cmd))
        gold = json.loads(
            subprocess.check_output(
                [
                    binary,
                    "replay",
                    d / "program.json",
                    d / "tape.json",
                    "audit",
                    "--ept",
                ]
            )
        )
        for k in ("schedule", "events", "rhs", "state_sha", "writes", "resumes"):
            assert capture[k] == gold[k], (name, k)
        if name == "cyk801":
            assert (
                gold["state_sha"]
                == json.loads(
                    (root / "oracle-survey/cykjson-rows/survey.json").read_text()
                )["state_sha"]
            )
        (d / "capture.json").write_text(json.dumps(capture))
        print(
            name,
            capture["runs"],
            capture["matches"],
            hashlib.sha256((d / "program.json").read_bytes()).hexdigest(),
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--extra-blind", type=int, nargs="*", default=[])
    p.add_argument("--cases", nargs="+")
    a = p.parse_args()
    main(a.root.resolve(), a.out.resolve(), a.extra_blind, a.cases)
