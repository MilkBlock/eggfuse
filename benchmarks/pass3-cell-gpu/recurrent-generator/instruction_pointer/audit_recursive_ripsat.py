"""Offline native composition witnesses, kept out of the policy and RL reward."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from entry_closure import Tape, named
from int_parameters import link_layouts
from protocol_experiment import dump
from receipt_bake import read, save
from receipt_takeover import replay_many
from recursive_train import binary, folder


def audit(data, catalog, case, output):
    exe = binary(data)
    d = folder(data, case)
    tape = Tape(d, exe)
    manifest = read(catalog)
    units = dict(link_layouts(tape.program, manifest))
    ids = sorted(units)
    tails = defaultdict(list)
    for i, uid in enumerate(ids):
        for seq in tape.occasions(units[uid]):
            tails[seq[-1]].append((i, seq))
    capture = read(d / "capture.json")
    replay = json.loads(subprocess.check_output([exe, "replay", d / "program.json",
        d / "tape.json", "audit", "--ept-origins"]))
    if replay["state_sha"] != capture["state_sha"]:
        raise ValueError("teacher replay failed")
    origins = dict(replay["ept"]["origins"])
    samples = {}
    for q in tape.tape:
        refs = list(map(named, q["parents"]))
        if len(refs) != 2 or not origins.get(q["token"]):
            continue
        left, right = refs
        if left[0] == right[0]:
            continue
        for role, (first, other) in enumerate(((left, right), (right, left))):
            for u in tails.get(first[0], []):
                if other[0] in u[1]:
                    continue
                partners = tails.get(other[0], ())
                key = "Extend"
                chosen = [u]
                for v in partners:
                    if set(u[1]).isdisjoint(v[1]):
                        key, chosen = "Compose", [u, v]
                        break
                if key not in samples:
                    samples[key] = (q, chosen)
        if len(samples) == 2:
            break
    results = {}
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "units.json"
        save(path, [units[i] for i in ids])
        for key, (q, chosen) in samples.items():
            check = replay_many(d, exe, path, chosen, tape.tape, capture)
            results[key] = dict(layouts=[ids[i] for i, _ in chosen],
                existing_steps=[s for _, s in chosen], suffix=q,
                suffix_effective_ops=origins[q["token"]], checks=check["checks"],
                native_accepted=check["accepted"])
    dump(output, results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("catalog", type=Path)
    p.add_argument("case")
    p.add_argument("output", type=Path)
    a = p.parse_args()
    audit(a.data, a.catalog, a.case, a.output)
