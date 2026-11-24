"""Offline, native-checked alternatives at the same accepted teacher root."""
from argparse import ArgumentParser
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
import json
import subprocess
from tempfile import TemporaryDirectory

import torch
from entry_closure import Tape
from entry_marginal import path_costs
from int_parameters import link_layouts
from receipt_bake import read, save
from receipt_takeover import replay_many
from recursive_train import binary


def disjoint_batches(cases):
    batches, occupied = [], []
    for uid, ts in cases:
        for i, used in enumerate(occupied):
            if used.isdisjoint(ts):
                break
        else:
            i = len(batches)
            batches.append([])
            occupied.append(set())
        batches[i].append((uid, ts))
        occupied[i].update(ts)
    return batches


def first_probe(tape, unit, root):
    rid, _, wires = unit[1]
    times = tape.schedule[rid]
    i = bisect_right(times, root["run"])
    if i == len(times):
        return None
    parents = []
    for owner, pc in wires:
        if owner < 0:
            parents.append(root["parents"][pc])
        else:
            assert owner == 0
            token = root["token"]
            version = tape.snap.version(token, pc, root["run"] + 1)
            if version is None:
                return None
            parents.append(dict(address=dict(token=token, op=pc), version=version))
    return dict(run=times[i], rule=rid, parents=parents)


def measure(data, folder, catalog, out):
    exe = binary(data)
    tape = Tape(folder, exe)
    units = dict(link_layouts(tape.program, read(catalog)))
    ids = sorted(units)
    index = {uid: i for i, uid in enumerate(ids)}
    cases = [(uid, ts) for uid in ids for ts in tape.occasions(units[uid])]
    positive = {(ts[0], uid) for uid, ts in cases}
    costs = path_costs(data, folder, {tok for _, ts in cases for tok in ts[1:]})
    reference = read(folder / "capture.json")
    results = defaultdict(dict)
    reasons = Counter()
    audits = []
    with TemporaryDirectory() as tmp:
        layouts = Path(tmp) / "units.json"
        save(layouts, [units[i] for i in ids])
        for group in disjoint_batches(cases):
            audit = replay_many(folder, exe, layouts, [(index[u], t) for u, t in group],
                                tape.tape, reference)
            audits.append(audit)
            for uid, ts in group:
                cost = sum((costs[t] for t in ts[1:]), Counter())
                results[ts[0]][uid] = [
                    cost["suppressed_b_proposals"] - (len(ts) - 1),
                    cost["removed_terminal_visits"] + cost["unary_event_skips"],
                ]
        probes, owners = [], []
        for uid, unit in units.items():
            for (token,) in tape.by_rule[unit[0][0]]:
                if (token, uid) in positive:
                    continue
                q = first_probe(tape, unit, tape.q[token])
                if q is None:
                    reasons["unobserved_first_request"] += 1
                    continue
                probes.append(dict(q, token=len(probes) + 1))
                owners.append((token, uid))
        probe = Path(tmp) / "probes.json"
        save(probe, dict(read(folder / "tape.json"), requests=probes))
        rep = json.loads(subprocess.check_output([
            exe, "replay", folder / "program.json", folder / "tape.json",
            "audit", "--recall", probe,
        ]))
        if (rep["unused_recall"] or len(rep["recall_verdicts"]) != len(probes)
                or rep["state_sha"] != reference["state_sha"]):
            raise ValueError("unverified alternative probes")
        for _, k, winner, reason in rep["recall_verdicts"]:
            reasons[reason] += 1
            if winner is None and reason != "off_reference":
                token, uid = owners[k - 1]
                # A native rejection consumes one request and skips no candidate.
                results[token][uid] = [-1, 0]
    save(out, dict(native_batches=audits, native_probe_reasons=reasons,
                   verified_full=len(cases), roots=results, state_sha=rep["state_sha"]))


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "folder", "catalog", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    measure(a.data, a.folder, a.catalog, a.out)
