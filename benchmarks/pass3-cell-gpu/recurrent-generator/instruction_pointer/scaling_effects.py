"""Paired causal forks on sampled training windows. Every compared name is executed alone."""

import hashlib
import json
import os
import pickle
import random
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import torch

from binding_egg import unpack
from ccp_v01 import Client
from credit_scale_buffer import submit
from discrete_draft import Cell
from int_parameters import digest, encode
from joint_cell_replay import target
from partner_index_worlds import args
from prefix_train import make
from scaling_archive import Archive, directory, load, program


def branch(a, p, b, index, phase, action, export):
    cmd = [
        a.runtime_binary,
        "online-ccp-v0.1",
        p,
        "-",
        "audit",
        "--export",
        export,
        "--ept-origins",
    ]
    transitions = []
    response = None
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        cli = Client(proc, 512, b["program"])
        try:
            i = -1
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                if i >= index:
                    transitions.append(
                        {
                            k: f[k]
                            for k in (
                                "run",
                                "epoch",
                                "rules",
                                "updates",
                                "retired",
                                "accepted",
                            )
                            if k in f
                        }
                    )
                if f.get("final_publication"):
                    continue
                i += 1
                cli.run, cli.epoch = f["run"], f["epoch"]
                if i <= index:
                    e = b["events"][i]
                    if any(f[k] != v for k, v in e["frame"].items()):
                        raise ValueError("native prefix frame differs")
                    for src, dst in (
                        ("generated", "response"),
                        ("assisted", "assisted_response"),
                    ):
                        if i == index and src == phase:
                            if action is not None:
                                [response] = submit(cli, [Cell(*action)], 128)
                            break
                        if (
                            submit(cli, [Cell(*target(t)) for t in e[src]], 128)
                            != e[dst]
                        ):
                            raise ValueError("native prefix replies differ")
                cli.seal()
            if proc.wait() or i < index:
                raise ValueError("incomplete native branch")
        finally:
            cli.close()
    g = json.loads(export.read_text())
    rows = frozenset(map(encode, g["rows"]))
    if len(rows) != len(g["rows"]):
        raise ValueError("duplicate export rows cannot be identified by set difference")
    # Conservative identity: retain named versions, retirements and schedule through the end.
    signature = digest([f["state_sha"], g["anchors"], transitions])
    gain = 0 if response is None else dict(f["ept"]["origins"]).get(response[0], 0)
    return rows, signature, response, gain


def collect(a):
    d = directory(a)
    archive = Archive(a, make(a, "rel").actor)
    bank = list(map(json.loads, (d / "archive.jsonl").read_text().splitlines()))
    groups = defaultdict(list)
    for r in bank:
        for i, phase, sha, count, _ in r["states"]:
            if 8 <= count <= 24:
                groups[r["program"]].append((r, i, phase, sha))
    rng = random.Random(58133)
    chosen = rng.sample(sorted(groups), min(256, len(groups)))
    path = d / "fork-effects.jsonl"
    done = (
        {r["program"] for r in map(json.loads, path.read_text().splitlines())}
        if path.exists()
        else set()
    )
    root = Path(os.environ["ARTIFACT_ROOT"])
    with tempfile.TemporaryDirectory() as tmp, path.open("a", buffering=1) as sink:
        for prog in chosen:
            r, i, phase, sha = rng.choice(groups[prog])
            if prog in done:
                continue
            b = load(root / r["path"])
            p = program(root, Path(r["path"]).parts[0], b["idx"])
            if hashlib.sha256(p.read_bytes()).hexdigest() != prog:
                raise ValueError("program digest differs")
            _, s, ts, _ = archive.rows(r["path"])[i, phase]
            if digest(s) != sha:
                raise ValueError("archive snapshot differs")
            export = Path(tmp) / "rows.json"
            base, _, _, _ = branch(a, p, b, i, phase, None, export)
            evidence = []
            for t in ts:
                actual, signature, rep, ops = branch(a, p, b, i, phase, t, export)
                extra, lost = actual - base, base - actual
                verified = rep[1] == 0 and ops > 0 and bool(extra) and not lost
                evidence.append(
                    [
                        t,
                        rep,
                        ops,
                        len(extra),
                        len(lost),
                        digest(sorted(extra)),
                        signature if verified else None,
                    ]
                )
            item = {
                "program": prog,
                "state": sha,
                "archive": r["path"],
                "index": i,
                "phase": phase,
                "branch": b["branch"],
                "tokens": evidence,
            }
            sink.write(json.dumps(item, separators=(",", ":")) + "\n")
    merged = {}
    for r in map(json.loads, path.read_text().splitlines()):
        proven = {
            (t[0], tuple(map(tuple, t[1]))): sig
            for t, _, _, _, _, _, sig in r["tokens"]
            if sig
        }
        if proven:
            merged[r["program"], r["state"]] = proven
    out = d / "fork-effects.pkl"
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(merged))
    tmp.replace(out)


if __name__ == "__main__":
    torch.set_num_threads(1)
    collect(args())
