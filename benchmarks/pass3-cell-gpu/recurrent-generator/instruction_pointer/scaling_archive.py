"""Verify native training-only archives and index decision states without duplicating Memory."""

import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from functools import lru_cache
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import torch

from binding_egg import unpack
from ccp_v01 import Client
from cell_kv_runtime import Instances
from cell_kv_world import World
from credit_scale_buffer import submit
from discrete_draft import Cell
from int_parameters import digest
from joint_cell_replay import target
from partner_index_worlds import args
from prefix_train import make
from rule_publication import publication_observer, read_rule_frame


def directory(a):
    d = a.out / "full-ce-scaling"
    d.mkdir(exist_ok=True)
    return d


def program(root, family, i):
    paths = [
        root / family / "dynamic",
        root / "data-scale-1126",
        root / family / "novel",
    ]
    for base in paths:
        p = base / "programs" / f"{i:04d}" / "program.json"
        if p.exists():
            return p
    raise FileNotFoundError((family, i))


def snapshot_key(s):
    return digest(s)


def load(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def verify(a, path, b):
    events = iter(b["events"])
    frames = iter(b["scheduler"])
    cmd = [a.runtime_binary, "online-ccp-v0.1", path, "-", "audit", "--ept-origins"]
    with (
        publication_observer(True) as (reader, _, env),
        subprocess.Popen(cmd, stdin=-1, stdout=-1, env=env) as proc,
    ):
        client = Client(proc, 512, b["program"])
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                if next(frames) != json.loads(reader.readline()):
                    raise ValueError("publication differs")
                if f.get("final_publication"):
                    continue
                e = next(events)
                if any(f[k] != v for k, v in e["frame"].items()):
                    raise ValueError("frame differs")
                client.run, client.epoch = f["run"], f["epoch"]
                for src, reply in (
                    ("generated", "response"),
                    ("assisted", "assisted_response"),
                ):
                    if (
                        submit(client, [Cell(*target(t)) for t in e[src]], 128)
                        != e[reply]
                    ):
                        raise ValueError("native replies differ")
                client.seal()
            if (
                proc.wait()
                or next(frames, None) is not None
                or next(events, None) is not None
                or f["state_sha"] != b["terminal"]
                or dict(f["ept"]["origins"]) != dict(b["origins"])
            ):
                raise ValueError("native terminal graph or origins differ")
        finally:
            client.close()


class Archive:
    def __init__(self, a, actor):
        self.a = a
        self.actor = actor
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(os.environ["ARTIFACT_ROOT"])
        self.world = lru_cache(maxsize=512)(self.world)
        self.rows = lru_cache(maxsize=4)(self.rows)

    def world(self, family, i, sha):
        p = program(self.root, family, i)
        raw = p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("Recipe digest differs")
        d = Path(self.tmp.name) / sha
        if not d.exists():
            d.mkdir()
            (d / "program.json").write_bytes(raw)
            (d / "contract.json").write_bytes(
                subprocess.check_output([self.a.runtime_binary, "receipt-contract", p])
            )
        return World(d, self.actor, sides="", entry_table=None)

    def rows(self, path):
        b = load(self.root / path)
        family = Path(path).parts[0]
        w = self.world(family, b["idx"], b["program"])
        frames = {r[0]: r for r in b["scheduler"]}
        mem = Instances(w, True)
        origins = dict(b["origins"])
        rows = {}
        for idx, e in enumerate(b["events"]):
            f = dict(e["frame"])
            f["rule_state"], f["check_dirty"] = read_rule_frame(
                StringIO(json.dumps(frames[f["run"]])), f
            )
            mem.update(f)
            cli = SimpleNamespace(run=f["run"], epoch=f["epoch"])
            for src, reply in (
                ("generated", "response"),
                ("assisted", "assisted_response"),
            ):
                snapshot = mem.snapshot(w, f)
                verified = set()
                for tok, rep in zip(e[src], e[reply], strict=True):
                    rid, refs = target(tok)
                    mem.acknowledge(cli, rid, refs, rep)
                    uid, status, *_ = rep
                    if not status:
                        mem.begin(uid, rid, refs)
                        if origins.get(uid, 0) > 0:
                            verified.add((rid, refs))
                omission = set()
                if src == "assisted" and e["stable"]:
                    omission = {target(tok) for tok, gain in e["omitted"] if gain > 0}
                ts = sorted(verified | omission)
                if ts:
                    types = {p[0]: p[3] for p in snapshot["ports"]}
                    for rid, refs in ts:
                        if (
                            rid not in snapshot["menu"]
                            or [types[p] for p in refs] != w.roles[rid]
                        ):
                            raise ValueError("target outside named and typed domain")
                    rows[idx, src] = (w, snapshot, ts, len(omission))
        return rows


def prepare(a):
    root = Path(os.environ["ARTIFACT_ROOT"])
    bank = Archive(a, make(a, "rel").actor)
    out = directory(a) / "archive.jsonl"
    done = {}
    if out.exists():
        done = {r["path"]: r for r in map(json.loads, out.read_text().splitlines())}
    with out.open("a", buffering=1) as sink:
        for family in ("transition-credit-1127", "credit-scaling-1126"):
            for path in sorted((root / family / "buffer").glob("*.json.gz")):
                rel = str(path.relative_to(root))
                fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
                if rel in done:
                    if fingerprint != done[rel]["sha"]:
                        raise ValueError("archive changed")
                    continue
                b = load(path)
                p = program(root, family, b["idx"])
                verify(a, p, b)
                rows = bank.rows(rel)
                summary = [
                    (i, phase, snapshot_key(s), len(t), om)
                    for (i, phase), (_, s, t, om) in rows.items()
                ]
                record = {
                    "path": rel,
                    "sha": fingerprint,
                    "program": b["program"],
                    "states": summary,
                    "generated": sum(len(e["generated"]) for e in b["events"]),
                    "assisted": sum(len(e["assisted"]) for e in b["events"]),
                }
                sink.write(json.dumps(record, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
