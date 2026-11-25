"""Replay each witnessed event projection against the native reference snapshot."""
from argparse import ArgumentParser
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from entry_closure import Tape, named
from entry_counterfactual import disjoint_batches
from int_parameters import link_layouts
from multi_entry import link_entries, resolve
from receipt_bake import read, save
from receipt_takeover import replay_many
from recursive_train import binary


class Published:
    def __init__(self, snapshot, run):
        self.snapshot, self.run = snapshot, run

    def get(self, address):
        version = self.snapshot.version(*address, self.run)
        return None if version is None else {"version": version}


def audit(data, folder, catalog, contracts, out):
    exe = binary(data)
    tape = Tape(folder, exe)
    manifest = read(catalog)
    entries = link_entries(tape.program, manifest, read(contracts), tape.rules.rules)
    bodies = defaultdict(list)
    units = dict(link_layouts(tape.program, manifest))
    paths = {}
    for uid, unit in units.items():
        for seq in tape.occasions(unit):
            bodies[seq[0]].append(uid)
            paths[uid, seq[0]] = seq
    probes, events, seen = [], [], set()
    for req in tape.tape:
        run, root = req["run"], req["rule"]
        for role, arg in enumerate(req["parents"]):
            owner, op, _ = named(arg)
            producer = tape.q.get(owner)
            if producer is None or producer["run"] >= run:
                continue
            for cid, contract in entries.get((root, role, producer["rule"], op), ()):
                event = (run, root, owner, cid)
                if event in seen:
                    continue
                seen.add(event)
                refs = resolve(contract["reads"], owner, list(map(named, producer["parents"])),
                               Published(tape.snap, run))
                if refs is None:
                    continue
                parents = [dict(address=dict(token=t, op=p), version=v) for t, p, v in refs]
                probes.append(dict(run=run, rule=root, parents=parents, token=len(probes) + 1))
                events.append(dict(run=run, rule=root, owner=owner, contract=cid))
    with TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probes.json"
        save(probe, dict(read(folder / "tape.json"), requests=probes))
        report = json.loads(subprocess.check_output([
            exe, "replay", folder / "program.json", folder / "tape.json", "audit", "--recall", probe
        ]))
    reference = read(folder / "capture.json")
    checks = {k: report[k] == reference[k] for k in ("state_sha", "schedule", "writes", "rhs", "events", "resumes")}
    if (not all(checks.values()) or report["unused_recall"] or
            sorted(p[1] for p in report["recall_verdicts"]) != list(range(1, len(probes) + 1))):
        raise ValueError("incomplete native projection replay")
    witnesses = {}
    for run, k, winner, status in report["recall_verdicts"]:
        event = events[k - 1]
        if event["run"] != run:
            raise ValueError("probe returned at wrong Run")
        event.update(status=status, winner=winner, observed_bodies=bodies.get(winner, []))
        if status == "match" and probes[k - 1]["parents"] == tape.q[winner]["parents"]:
            for uid in bodies.get(winner, []):
                witnesses.setdefault((uid, event["contract"]), paths[uid, winner])
    # Replay a whole body only where the projected entry supplied exactly the
    # signed boundary used in that replay. Different proofs may share a winner.
    ids = sorted(units)
    cases = sorted({(ids.index(uid), seq) for (uid, _), seq in witnesses.items()})
    with TemporaryDirectory() as tmp:
        layouts = Path(tmp) / "layouts.json"
        save(layouts, [units[i] for i in ids])
        for batch in disjoint_batches(cases):
            replay_many(folder, exe, layouts, batch, tape.tape, reference)
    save(out, dict(checks=checks, events=events,
                   verified_bodies=[[u, c, seq] for (u, c), seq in sorted(witnesses.items())]))


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "folder", "catalog", "contracts", "out"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    audit(args.data, args.folder, args.catalog, args.contracts, args.out)
