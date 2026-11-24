"""Match the source program, native return schema, depth and selection budget."""

import argparse
from collections import defaultdict
from pathlib import Path
import subprocess, json
from int_parameters import StructuralBake, link_layouts
from receipt_bake import external, read, save
from ripsat_layout import capture, signatures
from entry_ceiling import measure


def collect(folder, binary):
    p = read(folder / "program.json")
    native = json.loads(
        subprocess.check_output([binary, "receipt-contract", folder / "program.json"])
    )
    _, _, roots, _ = capture(folder, p, 8, grow_consumers=True, receipt_contract=native)
    choices = defaultdict(list)
    for variants in roots.values():
        for unit, occ in variants.items():
            choices[unit].extend(
                ts for _, ready, scheduled, ts in occ if ready and scheduled
            )
    return p, choices


def audit(root, binary, out):
    control = out / "trace-control"
    control.mkdir(exist_ok=True)
    program, choices = collect(root / "sum", binary)
    support = {
        u: {t: len(w) for ts in seq for (_, _, w), t in zip(u[1:], ts[1:], strict=True)}
        for u, seq in choices.items()
        if seq
    }
    before = len(support)
    units = []
    used = set()
    for _ in read(out / "catalog.json")["layouts"]:
        if not support:
            break

        def gain(u):
            extra = len(external(u)) - len(set(u[0][2]))
            return sum(n for t, n in support[u].items() if t not in used) - extra * len(
                choices[u]
            )

        best = max(support, key=lambda u: (gain(u), u))
        if gain(best) <= 0:
            break
        used.update(support.pop(best))
        units.append(best)
    catalog = dict(
        signatures=signatures(program),
        layouts=units,
        **StructuralBake(program).manifest(units),
    )
    save(control / "catalog.json", catalog)
    save(
        control / "population.json",
        dict(discovered=len(choices), train_ready=before, selected=len(units)),
    )
    for name in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        p, actual = (
            (program, choices) if name == "sum" else collect(root / name, binary)
        )
        occ = {
            uid: actual[tuple(u)]
            for uid, u in link_layouts(p, catalog)
            if actual.get(tuple(u))
        }
        save(control / (name + "-occasions.json"), occ)
        try:
            measure(root, binary, control, name)
        except ValueError as exc:
            save(control / (name + "-oracle-failed.json"), dict(reason=str(exc)))
        print(name, len(occ), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "binary", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    audit(a.root, a.binary, a.out)
