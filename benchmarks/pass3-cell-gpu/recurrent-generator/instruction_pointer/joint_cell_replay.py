"""Rebuild KV snapshots from older native rollout frames. Latent packets are never inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from collections import Counter
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
from joint_cell_corpus import folder, write_rows
from partner_index_worlds import args
from prefix_train import make
from rule_publication import publication_observer, read_rule_frame


def target(raw):
    rid, higher, refs = raw
    assert not higher
    return rid, tuple(map(tuple, refs))


def verify_archive(a, ir, buf):
    cmd = [a.runtime_binary, "online-ccp-v0.1", ir, "-", "audit", "--ept-origins"]
    events = iter(buf["events"])
    scheduler = iter(buf["scheduler"])
    requests = 0
    with (
        publication_observer(True) as (reader, _, env),
        subprocess.Popen(cmd, stdin=-1, stdout=-1, env=env) as proc,
    ):
        client = Client(proc, 512, buf["program"])
        try:
            for line in iter(proc.stdout.readline, b""):
                frame = json.loads(line)
                if "role" in frame:
                    break
                unpack(proc.stdout, frame)
                assert json.loads(reader.readline()) == next(scheduler)
                if frame.get("final_publication"):
                    continue
                event = next(events)
                assert all(frame[k] == v for k, v in event["frame"].items())
                client.run = frame["run"]
                client.epoch = frame["epoch"]
                cells = [Cell(*target(t)) for t in event["generated"]]
                assert submit(client, cells, 128) == event["response"]
                requests += len(cells)
                client.seal()
            assert (
                proc.wait() == 0
                and next(events, None) is None
                and next(scheduler, None) is None
            )
            assert frame["state_sha"] == buf["terminal"] and dict(
                frame["ept"]["origins"]
            ) == dict(buf["origins"])
        finally:
            client.close()
    return requests


def convert(a):
    d = folder(a)
    src = Path(os.environ["ARTIFACT_ROOT"]) / "transition-credit-1127"
    actor = make(a, "rel").actor
    report = []
    for archive in sorted((src / "buffer").glob("*-2-*.json.gz"))[:32]:
        buf = json.load(gzip.open(archive, "rt"))
        idx = buf["idx"]
        ir = src / "dynamic/programs" / f"{idx:04d}" / "program.json"
        assert hashlib.sha256(ir.read_bytes()).hexdigest() == buf["program"]
        verified = verify_archive(a, ir, buf)
        dest = d / f"legacy-{idx}"
        dest.mkdir(exist_ok=True)
        (dest / "program.json").write_bytes(ir.read_bytes())
        (dest / "contract.json").write_bytes(
            subprocess.check_output([a.runtime_binary, "receipt-contract", ir])
        )
        w = World(dest, actor, entry_table=None, sides="")
        mem = Instances(w, True)
        counts = Counter()
        rows = []
        frames = {q[0]: q for q in buf["scheduler"]}
        ledger = dict(buf["origins"])
        for e in buf["events"]:
            f = e["frame"]
            f["rule_state"], f["check_dirty"] = read_rule_frame(
                StringIO(json.dumps(frames[f["run"]])), f
            )
            mem.update(f)
            s = mem.snapshot(w, f)
            client = SimpleNamespace(run=f["run"], epoch=f["epoch"])
            assert not e["assisted"] and not e["assisted_response"]
            issued = set()
            omitted = set()
            for tok, rep in zip(e["generated"], e["response"], strict=True):
                rid, refs = target(tok)
                uid, status, *_ = rep
                mem.acknowledge(client, rid, refs, rep)
                if not status:
                    mem.begin(uid, rid, refs)
                    if ledger.get(uid, 0) > 0:
                        issued.add((rid, refs))
            for tok, gain in e["omitted"]:
                assert gain > 0 and e["stable"]
                omitted.add(target(tok))
            assert not issued & omitted
            ports = {p[0]: p[3] for p in s["ports"]}
            for rid, refs in issued | omitted:
                assert rid in s["menu"] and all(
                    ports[r] == t for r, t in zip(refs, w.roles[rid], strict=True)
                )
            counts["replies"] += len(e["generated"])
            if (issued or omitted) and len(s["request_receipts"]) <= 2048:
                rows.append((s, sorted(issued | omitted)))
                counts.update(issued=len(issued), omitted=len(omitted))
        write_rows(dest / "rows.pkl.gz", rows)
        report.append(
            dict(
                idx=idx,
                verified_native_requests=verified,
                states=len(rows),
                counts=counts,
                signature=buf["signature"],
                program=buf["program"],
                archive=archive.name,
            )
        )
    (d / "legacy.json").write_text(json.dumps(report))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        convert(args())
