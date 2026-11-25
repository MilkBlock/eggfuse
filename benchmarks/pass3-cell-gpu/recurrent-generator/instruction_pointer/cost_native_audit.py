"""Fork the measured independent trajectory offline and track exact witnesses through B."""

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from cell_stream import CellStream
from entry_closure import named
from event_addresses import Directory
from recursive_rollout import get_policy
from recursive_train import binary, folder, read


def find_targets(data, store, case):
    tape = store / f"{case}-issued.json"
    d = folder(data, case)
    exe = binary(data)
    z = np.load(store / f"{case}-ledger.npz")
    costs = z["depth"][:, :, 1].sum(1)
    order = np.argsort(-costs, kind="stable")
    ids = order[: 1 + np.searchsorted(costs[order].cumsum(), costs.sum() * 0.95)]
    meta = z["meta"]
    runs = sorted(set(meta[ids, 0].tolist()))
    root = {
        (int(run), int(r), int(j), int(t), int(pc), int(v)): int(i)
        for i in ids
        for run, r, j, t, pc, v in [meta[i, :6]]
    }
    probes = []
    mappings = defaultdict(list)
    outcomes = {}
    for run in runs:
        proc = subprocess.run(
            [exe, "replay", d / "program.json", tape, "time", str(run - 1), "--audit-next-proofs"],
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            outcomes[run] = {"error": proc.stderr.decode()[-300:]}
            continue
        req = json.loads(proc.stdout)
        rules = Counter(q["rule"] for q in req)
        outcomes[run] = {"native_named_bindings": len(req), "rules": dict(rules)}
        for q in req:
            parents = tuple(map(named, q["parents"]))
            match = [
                (root[key], j) for j, ref in enumerate(parents) if (key := (run, q["rule"], j, *ref)) in root
            ]
            if match:
                q["token"] = len(probes) + 1
                if q["run"] != run:
                    raise ValueError("unmatched fork")
                probes.append(q)
                mappings[run].append((q, match, parents))
    memory = store / f"{case}-native-memory.jsonl"
    probe = store / f"{case}-canonical-probes.json"
    gold = read(tape)
    gold["requests"] = probes
    probe.write_text(json.dumps(gold))
    rep = json.loads(
        subprocess.check_output(
            [exe, "replay", d / "program.json", tape, "audit", "--memory", memory, "--recall", probe]
        )
    )
    if rep["state_sha"] != read(store / f"{case}-profile-0.json")["state_sha"] or rep["unused_recall"]:
        raise ValueError("canonical audit changed baseline state")
    verdict = {i: (owner, why) for _, i, owner, why in rep["recall_verdicts"]}
    policy = get_policy(data, d, "free", "multi")
    rd, model = policy.reader, policy.model
    mem = Directory(rd, Counter())
    evidence = []
    for line in memory.open():
        frame = json.loads(line)
        run = frame["run"]
        rd.advance(frame)
        group = defaultdict(list)
        for q, matches, refs in mappings.get(run, ()):
            for i, j in matches:
                group[q["rule"], j].append((i, q, refs))
        for (r, j), rows in group.items():
            seq = mem.order(r, j)
            ptr = CellStream(
                rd,
                model,
                r,
                dict(frame["rules"])[r],
                Counter(),
                order=seq,
                role_ports=lambda t: mem.bank(t).ports,
            )
            ptr.prepare()
            paths = np.asarray(
                [[mem.bank(mem.roles[r][k]).positions[refs[k][:2]] for k in seq] for _, _, refs in rows],
                dtype=np.int64,
            )
            h = model.start(rd.meta(r)).expand(len(rows), -1)
            loss = [None] * len(rows)
            for depth, k in enumerate(seq):
                if depth:
                    post, lo, n = mem.window(r, seq[:depth], k, paths[:, :depth])
                    if post is not None:
                        for i, p in enumerate(paths[:, depth]):
                            if loss[i] is None and p not in post[lo[i] : lo[i] + n[i]]:
                                loss[i] = "bucket"
                score, h = ptr.logits(h, depth, torch.from_numpy(paths[:, : depth + 1]))
                if depth:
                    for i in np.flatnonzero(score.numpy() < 0):
                        if loss[i] is None:
                            loss[i] = "prefix" if depth + 1 < len(seq) else "terminal"
            for idx, (eid, q, refs) in enumerate(rows):
                owner, why = verdict[q["token"]]
                evidence.append([eid, why, owner, loss[idx], refs])
    (store / f"{case}-exact-audit.json").write_text(json.dumps({"runs": outcomes, "witnesses": evidence}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    with torch.no_grad():
        for c in a.cases:
            find_targets(a.data, a.store, c)
