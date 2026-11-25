"""Offline tape witness audit for the static natural-workload menus, followed by a native takeover replay."""

import argparse
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from discrete_cells import load_enc
from entry_closure import Tape
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from scaling_bake import save
from scaling_native import menus


def audit(args, case):
    d = folder(args.root, case)
    exe = binary(args.root)
    contract = json.loads(subprocess.check_output([exe, "receipt-contract", d / "program.json"]))
    enc, _ = load_enc(read(d / "program.json"), args.actor)
    excluded = set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"])
    tape = Tape(d, exe)
    results = {}
    for mode in ("small", "flat", "wide"):
        data = []
        best = None
        for r, unit in menus(contract, enc, d, mode, excluded, 256).items():
            starts = tape.by_rule[r]
            live = list(starts)
            depth = int(bool(live))
            for step in unit[1:]:
                live = [success for ts in live if (success := tape.extend(ts, step))]
                if not live:
                    break
                depth += 1
            data.append(
                dict(
                    root=r,
                    size=len(unit),
                    arity=len(unit[0][2]),
                    roots=len(starts),
                    deepest=depth,
                    complete=len(live),
                )
            )
            if live and (best is None or len(unit) > len(best[0])):
                best = unit, live[0]
        cert = None
        if best:
            with TemporaryDirectory(dir=args.out) as tmp:
                layout = Path(tmp) / "layout.json"
                save(layout, [best[0]])
                cert = replay_many(d, exe, layout, [(0, best[1])], tape.tape, read(d / "capture.json"))
                cert["size"] = len(best[0])
                cert["root"] = best[0][0][0]
        results[mode] = dict(layouts=data, certificate=cert)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "out", "actor"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    report = {}
    with torch.no_grad():
        for case in ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119"):
            report[case] = audit(a, case)
            save(a.out / "natural-witness.json", report)
