"""Bound the non-overlapping certificate population, then force a feasible packing."""

import argparse
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from entry_closure import savings, named
from receipt_bake import external
import json, subprocess
from int_parameters import link_layouts
from receipt_bake import read, save
from receipt_takeover import replay_many


def pack(units, occ):
    items = [(u, tuple(ts)) for u, seq in occ.items() for ts in seq]
    items.sort(key=lambda x: (-savings(units[x[0]]), -len(x[1]), x[1], x[0]))
    used = set()
    result = []
    for u, ts in items:
        if used.isdisjoint(ts):
            result.append((u, ts))
            used.update(ts)
    return result


def measure(root, binary, out, name):
    folder = root / name
    p = read(folder / "program.json")
    manifest = read(out / "catalog.json")
    units = dict(link_layouts(p, manifest))
    occ = {int(u): seq for u, seq in read(out / (name + "-occasions.json")).items()}
    cases = pack(units, occ)
    uids = sorted({u for u, _ in cases})
    remap = {u: i for i, u in enumerate(uids)}
    tape = read(folder / "tape.json")["requests"]
    by_token = {q["token"]: q for q in tape}
    unique = {t for values in occ.values() for ts in values for t in ts[1:]}
    with TemporaryDirectory() as tmp:
        d = Path(tmp) / "layouts.json"
        save(d, [units[u] for u in uids])
        native = replay_many(
            folder,
            binary,
            d,
            [(remap[u], ts) for u, ts in cases],
            tape,
            read(folder / "capture.json"),
        )
    children = [t for _, ts in cases for t in ts[1:]]
    wire_contract = json.loads(
        subprocess.check_output([binary, "receipt-contract", folder / "program.json"])
    )
    repairs = {ev["token"]: ev for ev in read(folder / "tape.json")["repair_events"]}
    entries = Counter()
    returns = Counter()
    eligible_roots = set()
    for uid, ts in cases:
        seen = set()
        for k, (_, _, wires) in enumerate(units[uid]):
            q = by_token[ts[k]]
            for role, ((owner, pc), arg) in enumerate(
                zip(wires, q["parents"], strict=True)
            ):
                t, op, _ = named(arg)
                required = wire_contract["rules"][q["rule"]]["inputs"][role]["table"]
                if owner >= 0:
                    site = wire_contract["rules"][by_token[ts[owner]]["rule"]][
                        "outputs"
                    ][str(pc)]
                    if site["table"] != required:
                        raise ValueError("interior receipt type mismatch")
                    returns[site["producer"]] += 1
                elif pc not in seen:
                    seen.add(pc)
                    if t in repairs:
                        ev = repairs[t]
                        if (
                            wire_contract["repair_outputs"][str(ev["merge_table"])][
                                str(op)
                            ]
                            != required
                            or op not in ev["operations"]
                            or ev["visible_from_run"] > by_token[ts[0]]["run"]
                        ):
                            raise ValueError("entry assumes unpublished repair output")
                        entries["published_repair"] += 1
                        eligible_roots.add(ts[0])
                    else:
                        entries["initial" if t < 0 else "generated"] += 1
    extras = sum(len(external(units[u])) - len(set(units[u][0][2])) for u, _ in cases)
    save(
        out / (name + "-oracle.json"),
        dict(
            upper_distinct_interior=len(unique),
            upper_named_operands=sum(len(by_token[t]["parents"]) for t in unique),
            feasible_instances=len(cases),
            internal_requests=len(children),
            external_request_saving=len(children),
            neural_reference_selections_replaced=sum(
                len(by_token[t]["parents"]) for t in children
            ),
            extra_external_bindings=extras,
            net_named_selections_replaced=sum(
                len(by_token[t]["parents"]) for t in children
            )
            - extras,
            boundary_by_producer=entries,
            internal_reads_by_producer=returns,
            instances_with_repair_boundary=len(eligible_roots),
            source_run_synchronizations_saved=0,
            native=native,
            packed=cases,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "binary", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    for name in a.cases:
        measure(a.root, a.binary, a.out, name)
