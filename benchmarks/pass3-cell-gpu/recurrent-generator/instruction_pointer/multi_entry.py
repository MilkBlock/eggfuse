"""Bake alternative single-owner entry projections for an unchanged layout body."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess

from entry_closure import Tape, named
from int_parameters import link_layouts
from receipt_bake import read, save
from recursive_train import binary
from ripsat_layout import signatures


def paths_from_instance(parents, role, producer):
    """An offline witness supplies addresses; no relation is enumerated online."""
    trigger = parents[role][0]
    prior = list(map(named, producer["parents"]))
    paths = []
    for ref in parents:
        if ref[0] == trigger:
            paths.append(("return", ref[1]))
        elif ref in prior:
            paths.append(("input", prior.index(ref)))
        else:
            return None
    return tuple(paths)


def check_types(rules, root, role, producer, op, paths):
    consumer = rules[root]["inputs"]
    source = rules[producer]
    if not 0 <= role < len(consumer) or len(paths) != len(consumer) or tuple(paths[role]) != ("return", op):
        raise ValueError("entry must bind every role and return its triggering port")
    for (kind, at), target in zip(paths, consumer, strict=True):
        if at < 0:
            raise ValueError("negative entry coordinate")
        if kind == "return":
            origin = source["outputs"][str(at)]
        elif kind == "input":
            origin = source["inputs"][at]
        else:
            raise ValueError("unknown entry coordinate")
        if origin["table"] != target["table"]:
            raise ValueError("entry table mismatch")


def compile_entries(data, folder, catalog, out):
    manifest = read(catalog)
    exe = binary(data)
    tape = Tape(folder, exe)
    sigs = signatures(tape.program)
    units = dict(link_layouts(tape.program, manifest))
    roots = {u[0][0] for u in units.values()}
    capture = read(folder / "capture.json")
    replay = json.loads(subprocess.check_output([
        exe, "replay", folder / "program.json", folder / "tape.json", "audit"
    ]))
    checks = {k: replay[k] == capture[k] for k in ("schedule", "state_sha", "rhs", "writes", "events", "resumes")}
    if not all(checks.values()) or replay["counts"]["accepted"] != len(tape.tape):
        raise ValueError("entry witnesses did not survive native replay")
    layouts_at = defaultdict(set)
    for uid, u in units.items():
        for seq in tape.occasions(u):
            layouts_at[seq[0]].add(uid)
    counts = Counter()
    completions = defaultdict(Counter)
    example = {}
    for q in tape.tape:
        r = q["rule"]
        if r not in roots or len(q["parents"]) < 2:
            continue
        refs = tuple(map(named, q["parents"]))
        for j, (owner, op, _) in enumerate(refs):
            producer = tape.q.get(owner)
            if producer is None or producer["run"] >= q["run"]:
                continue
            paths = paths_from_instance(refs, j, producer)
            if paths is None:
                continue
            src = producer["rule"]
            check_types(tape.rules.rules, r, j, src, op, paths)
            key = (r, j, src, op, paths)
            counts[key] += 1
            completions[key].update(layouts_at[q["token"]])
            example.setdefault(key, [owner, q["token"], q["run"]])
    entries = []
    for key in sorted(counts):
        r, j, src, op, paths = key
        entries.append(dict(root=sigs[r], role=j, producer=sigs[src], event_op=op,
                            reads=paths, verified_roots=counts[key], witness=example[key],
                            observed_complete_bodies=completions[key]))
    save(out, dict(schema="recipe-entry-contracts/v1", body_keys=manifest["structural_keys"],
                   default_entry="named_root_roles", entries=entries, native_checks=checks))


def link_entries(program, manifest, contracts, receipt_rules):
    if contracts["schema"] != "recipe-entry-contracts/v1" or contracts["body_keys"] != manifest["structural_keys"]:
        raise ValueError("entry contracts and body catalog differ")
    rules = defaultdict(list)
    for rid, sig in enumerate(signatures(program)):
        rules[sig].append(rid)
    choices = defaultdict(list)
    for cid, c in enumerate(contracts["entries"]):
        root, source = rules[c["root"]], rules[c["producer"]]
        if len(root) == len(source) == 1:
            key = root[0], c["role"], source[0], c["event_op"]
            check_types(receipt_rules, *key, c["reads"])
            choices[key].append((cid, c))
    # One statically selected path per dispatch. Conflicting contracts remain
    # independently addressable. Never probe the menu for a matching instance.
    return {k: sorted(v, key=lambda item: (-item[1]["verified_roots"], item[0]))
            for k, v in choices.items()}


def resolve(reads, token, original, visible):
    refs = []
    for kind, at in reads:
        if at < 0:
            raise ValueError("negative entry coordinate")
        if kind == "input":
            if at >= len(original) or (len(original[at]) == 4 and original[at][3] >= 0):
                return None
            t, op, v = map(int, original[at][:3])
            row = visible.get((t, op))
            if row is None or row["version"] != v:
                return None
        elif kind == "return":
            t, op = token, at
            row = visible.get((t, op))
            if row is None:
                return None
            v = row["version"]
        else:
            raise ValueError("unknown source")
        refs.append((t, op, v))
    return tuple(refs)


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "folder", "catalog", "output"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    compile_entries(a.data, a.folder, a.catalog, a.output)
