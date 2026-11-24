"""Offline census of redundant roles and previously witnessed parent references."""
import argparse
from collections import Counter
import json
from pathlib import Path


def audit(directory):
    program = json.loads((directory / "program.json").read_bytes())
    tape = json.loads((directory / "tape.json").read_bytes())
    plans = []
    for rule in program["recipe"]["rules"]:
        seen = {}
        copies = []
        for atom in rule["query"]:
            if "table" not in atom["call"]:
                continue
            key = json.dumps(atom, sort_keys=True)
            role = len(copies)
            copies.append(seen.setdefault(key, role))
        plans.append(copies)
    totals = Counter()
    published = {}
    for request in tape["requests"]:
        refs = request["parents"]
        plan = plans[request["rule"]]
        assert len(plan) == len(refs)
        totals["requests"] += 1
        totals["named_inputs"] += len(refs)
        for j, i in enumerate(plan):
            if i != j:
                totals["identical_atom_roles"] += 1
                totals["same_receipt_for_identical_atom"] += refs[i] == refs[j]
        # An existing producer's own input receipt may also be used by its
        # consumer. This is opportunity only: projection needs a typed Bake
        # proof and the projected receipt must still be visible on use.
        owners = [ref["address"]["token"] for ref in refs]
        totals["roles_beyond_distinct_producers"] += len(refs) - len(set(owners))
        for j, ref in enumerate(refs):
            if any(ref in published.get(other["address"]["token"], ())
                   for i, other in enumerate(refs) if i != j):
                totals["roles_witnessed_by_another_parent"] += 1
        published[request["token"]] = refs
    return dict(totals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directories", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps({p.name: audit(p) for p in args.directories}, indent=2))
