"""Mine connected teacher subgraphs offline. Only training graphs supply the Bake catalog."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from protocol_experiment import dump
from recursive_train import read, folder
from ripsat_layout import capture, signatures

SIZES = (8, 16, 32)


def audit(dataset, donor, keep=None):
    refs, _, roots, _ = capture(dataset, donor, max(SIZES), grow_consumers=True)
    frequencies = Counter()
    eligible = Counter()
    external = Counter()
    occurrences = defaultdict(list)
    for root, choices in roots.items():
        for unit, items in choices.items():
            n = len(unit)
            if n not in SIZES:
                continue
            for boundary, ready, first, tokens in items:
                external[n, len(boundary)] += 1
                frequencies[unit] += 1
                if not (ready and first):
                    continue
                eligible[unit] += 1
                if keep is None or unit in keep:
                    occurrences[unit].append((root, tokens))
    return refs, frequencies, eligible, external, occurrences


def root_only(u):
    w = u[0][2]
    return w == tuple((-1, j) for j in range(len(w))) and all(
        s < len(w) for _, _, wires in u for owner, s in wires if owner < 0
    )


def summary(case, result, catalog):
    refs, freq, ready, ext, occ = result
    rows = []
    for n in SIZES:
        candidates = [u for u in ready if len(u) == n]
        present = [u for u in candidates if u in catalog]
        matched = [(r, t) for u in present for r, t in occ[u]]
        touched = set(x for _, t in matched for x in t[1:])
        taken = set()
        nonoverlap = 0
        for _, t in sorted(matched):
            if taken.isdisjoint(t):
                taken.update(t)
                nonoverlap += 1
        rows.append(
            dict(
                size=n,
                observed=sum(v for u, v in freq.items() if len(u) == n),
                eligible=sum(ready[u] for u in candidates),
                unique=len(candidates),
                eligible_root_only=sum(ready[u] for u in candidates if root_only(u)),
                frozen_matches=len(matched),
                matched_templates=len(present),
                optimistic_distinct_nonroot_steps=len(touched),
                greedy_disjoint_instances=nonoverlap,
                greedy_nonroot_steps=nonoverlap * (n - 1),
                external_refs_histogram={
                    str(k): v for (size, k), v in sorted(ext.items()) if size == n
                },
            )
        )
    return dict(case=case, reference_commits=len(refs), sizes=rows)


def main(root, out, donor_dir):
    donor = read(donor_dir / "program.json")
    train = {}
    count = Counter()
    for name, d in [("sum-bits", donor_dir), ("loopfact", folder(root, "loopfact"))]:
        result = audit(d, donor)
        train[name] = result
        count.update(result[2])
    # Freeze the deployment menu from training only. Root-addressable units can
    # run from a single emitted boundary; all internal references remain wired.
    units = [u for u, v in count.most_common() if root_only(u)]
    dump(
        out / "large-bake.json",
        dict(
            signatures=signatures(donor),
            units=units,
            frequencies=[count[u] for u in units],
        ),
    )
    catalog = set(units)
    rows = [summary(n, r, catalog) for n, r in train.items()]
    for case in ("fact", "sum-divisors"):
        rows.append(summary(case, audit(folder(root, case), donor, catalog), catalog))
    dump(out / "large-audit.json", rows)
    print(
        [
            (
                r["case"],
                [
                    (x["size"], x["eligible_root_only"], x["frozen_matches"])
                    for x in r["sizes"]
                ],
            )
            for r in rows
        ],
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "out", "donor"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    main(a.root, a.out, a.donor)
