"""Offline causal replay of explicitly named witnesses through the unmodified CCP v0.1 runtime."""

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np

from boundary_inputs import CASE, binary, folder, read
from ccp_v01 import Client, offline_repairs, read_repairs
from cell_transaction import STATUS, memory_frame
from entry_closure import named
from scaling_bake import save

PRIOR = Path("run-recall/startup-boundaries")
CHECKS = ("state_sha", "schedule", "writes", "rhs", "resumes", "events")


def record_publication(current, history, address, version):
    if current.get(address) != version:
        history[address].append(version)
    current[address] = version


def compile_dag(nodes, frames):
    """Pin each wire to the observed publication ordinal on that named port."""
    history = defaultdict(list)
    current = {}
    by_run = defaultdict(list)
    for q in nodes:
        by_run[q["run"]].append(q)
    obligations = {}
    for f in frames:
        for a in f["retired"]:
            current.pop((a["token"], a["op"]), None)
        for a, row in f["updates"]:
            record_publication(current, history, (a["token"], a["op"]), row["version"])
        for q in by_run[f["run"]]:
            wire = []
            for p in q["parents"]:
                t, op, v = named(p)
                if current.get((t, op)) != v:
                    raise ValueError(("teacher publication missing", q, p))
                wire.append((t, op, len(history[t, op])))
            obligations[q["token"]] = wire
    if len(obligations) != len(nodes):
        raise ValueError("missing consumer publication frame")
    return obligations


def add_frame(h, run, epoch, rules, updates, retired, accepted):
    payload = [run, epoch, rules, updates, retired, accepted]
    h.update(json.dumps(payload, separators=(",", ":")).encode())
    h.update(b"\n")


def reference_stream(path):
    h = hashlib.sha256()
    with path.open() as stream:
        for f in map(json.loads, stream):
            updates = [
                [
                    a["token"],
                    a["op"],
                    r["table"],
                    r["version"],
                    int(r["forwarded"]),
                    r["hashes"],
                ]
                for a, r in f["updates"]
            ]
            add_frame(
                h,
                f["run"],
                f["epoch"],
                f["rules"],
                updates,
                [[a["token"], a["op"]] for a in f["retired"]],
                [[q["token"], q["rule"]] for q in f["accepted"]],
            )
    return h.hexdigest()


def replay(
    data,
    tape,
    nodes,
    obligations,
    mode,
    stop=None,
    causes=None,
    precedes=None,
    groups=None,
    observed=(),
    observer=None,
):
    """Schedule-gated event modes never read the teacher Run or absolute version for dispatch."""
    full = mode in ("full_order", "full_groups")
    stream_hash = hashlib.sha256()
    ordered = mode in ("full_order", "region_order")
    by_run = defaultdict(list)
    if ordered:
        for q in nodes:
            by_run[q["run"]].append(q)
    pending = {q["token"]: q for q in nodes}
    actual = {}
    reverse = {}
    live = {}
    history = defaultdict(list)
    issued = {}
    advanced_by = {}
    committed = set()
    stage = 0
    repairs = []
    observed = set(observed)
    returns = {}
    digest = tape["program_sha256"]
    cmd = [
        binary(data),
        "online-ccp-v0.1",
        folder(data, CASE) / "program.json",
        "-",
        "audit",
    ]
    if stop:
        cmd.append(str(stop))
    cmd.append("--ept")
    start = perf_counter()
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        client = Client(proc, 1024, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    end = f
                    break
                client.run, client.epoch = f["run"], f["epoch"]
                rows, hashes, retired, published = memory_frame(proc.stdout, f)
                repairs.extend(offline_repairs([read_repairs(proc.stdout, f)]))
                confirmed = frozenset(
                    reverse[tid] for tid, _ in published.tolist() if tid in reverse
                )
                committed.update(confirmed)
                if groups and stage < len(groups) and set(groups[stage]) <= committed:
                    stage += 1
                for tid, op in retired.tolist():
                    live.pop((reverse.get(tid, tid), op), None)
                offsets = []
                offset = 0
                for tid, op, tab, v, forwarded, end_offset in rows.tolist():
                    if full:
                        offsets.append(
                            [
                                tid,
                                op,
                                tab,
                                v,
                                forwarded,
                                hashes[offset:end_offset].tolist(),
                            ]
                        )
                    addr = reverse.get(tid, tid), op
                    if addr[0] in confirmed and addr[0] in observed:
                        returns.setdefault(addr[0], {})[op] = [
                            tab,
                            v,
                            forwarded,
                            hashes[offset:end_offset].tolist(),
                        ]
                    offset = end_offset
                    if live.get(addr) != v:
                        advanced_by[addr] = confirmed
                    record_publication(live, history, addr, v)
                if observer is not None:
                    observer(f, rows, hashes, retired, published, reverse)
                if f["final_publication"]:
                    continue
                if full:
                    add_frame(
                        stream_hash,
                        client.run,
                        client.epoch,
                        f["rules"],
                        offsets,
                        retired.tolist(),
                        published.tolist(),
                    )
                scheduled = dict(f["rules"])
                if groups:
                    candidates = (
                        [pending[k] for k in groups[stage] if k in pending]
                        if stage < len(groups)
                        else []
                    )
                else:
                    candidates = (
                        by_run[client.run] if ordered else list(pending.values())
                    )
                batch = []
                for q in candidates:
                    token = q["token"]
                    if q["rule"] not in scheduled:
                        continue
                    if precedes and not precedes.get(token, set()) <= committed:
                        continue
                    refs = []
                    if ordered:
                        for p in q["parents"]:
                            t, pc, v = named(p)
                            # An unproduced positive owner cannot alias a new wire ID.
                            refs.append(
                                (
                                    actual.get(t, t if t < 0 else (1 << 54) + t),
                                    pc,
                                    v,
                                    -1,
                                )
                            )
                    else:
                        for i, (t, pc, ordinal) in enumerate(obligations[token]):
                            a = t, pc
                            if a not in live or (t > 0 and t not in actual):
                                break
                            needed = 1 if mode == "first" else ordinal
                            if (
                                mode in ("causal", "ordered_causes")
                                and (token, i) in causes
                            ):
                                if not causes[token, i] <= advanced_by.get(
                                    a, frozenset()
                                ):
                                    break
                            elif mode != "latest" and len(history[a]) != needed:
                                break
                            refs.append((actual.get(t, t), pc, live[a], -1))
                        else:
                            batch.append((q, refs))
                        continue
                    batch.append((q, refs))
                for offset in range(0, len(batch), client.capacity):
                    chunk = batch[offset : offset + client.capacity]
                    ops, refs = [], []
                    for q, args in chunk:
                        refs.extend(args)
                        ops.append((0, 0, q["rule"], -1, len(refs)))
                    replies = client.submit(
                        ops, np.asarray(refs, dtype=np.int64).reshape(-1, 4)
                    ).tolist()
                    for (q, _), (tid, status, _, _) in zip(chunk, replies, strict=True):
                        k = q["token"]
                        pending.pop(k)
                        issued[k] = [client.run, STATUS[status]]
                        if status == 0:
                            actual[k] = tid
                            reverse[tid] = k
                client.seal()
            else:
                raise ValueError("missing terminal report")
        finally:
            if proc.poll() is None and "end" not in locals():
                proc.kill()
            proc.stdin.close()
            client.close()
        if proc.wait():
            raise ValueError("native execution failed")
    result = dict(
        mode=mode,
        paid=client.paid,
        accepted=len(actual),
        verdicts=dict(client.verdicts),
        pending=len(pending),
        native_runs=end["runs"],
        state_sha=end["state_sha"],
        wall=perf_counter() - start,
        effective=sum(end["ept"]["signed_external"]),
        repair_count=len(repairs),
        issued=issued,
    )
    if observed:
        result["first_returns"] = returns
    if mode in ("full_order", "full_groups"):
        ref = read(folder(data, CASE) / "capture.json")
        result["checks"] = {k: end[k] == ref[k] for k in CHECKS}
        result["publication_sha256"] = stream_hash.hexdigest()
        result["checks"]["all_publications"] = (
            stream_hash.hexdigest()
            == reference_stream(folder(data, CASE) / "memory.jsonl")
        )
        result["checks"]["repair_events"] = repairs == tape["repair_events"]
        result["checks"]["identity"] = all(k == v for k, v in actual.items())
        if mode == "full_order" and (
            not all(result["checks"].values()) or len(actual) != len(nodes)
        ):
            raise ValueError(
                ("CCP positive control failed", result["checks"], result["verdicts"])
            )
    else:
        blocked = {}
        for k in pending:
            unmet = []
            for i, (t, pc, n) in enumerate(obligations[k]):
                addr = t, pc
                expected = (
                    (causes or {}).get((k, i))
                    if mode in ("causal", "ordered_causes")
                    else None
                )
                actual_writers = advanced_by.get(addr, frozenset())
                unavailable = addr not in live or (t > 0 and t not in actual)
                if expected is not None:
                    missing = not expected <= actual_writers
                elif ordered or mode == "latest":
                    missing = False
                else:
                    missing = len(history[addr]) != (1 if mode == "first" else n)
                if unavailable or missing:
                    unmet.append(
                        dict(
                            owner=t,
                            op=pc,
                            teacher_ordinal=n,
                            observed=len(history[addr]),
                            live_version=live.get(addr),
                            expected_writers=sorted(expected or ()),
                            absent_writers=sorted((expected or set()) - actual_writers),
                        )
                    )
            blocked[k] = unmet
        result["blocking_wires"] = blocked
    return result


def main(data, out):
    d = folder(data, CASE)
    tape = read(d / "tape.json")
    nodes = tape["requests"]
    mapping = {q["token"]: q for q in nodes}
    rows = [
        r for r in read(PRIOR / "boundaries.json") if r["label"] == "both_ancestries"
    ]
    with (d / "memory.jsonl").open() as stream:
        wires = compile_dag(nodes, map(json.loads, stream))
    control = replay(data, tape, nodes, wires, "full_order")
    control.pop("issued")
    save(out / "control.json", control)
    print("exact control", control, flush=True)
    for r in rows:
        root = r["root"]
        targets = r["region"]["tokens"]
        group = [mapping[k] for k in targets]
        results = []
        for mode in ("region_order", "first", "latest", "ordinal"):
            row = replay(data, tape, group, wires, mode)
            row["complete"] = row["accepted"] == len(group)
            results.append(row)
        save(
            out / f"closure-{root}.json",
            dict(root=root, wires={k: wires[k] for k in targets}, results=results),
        )
        print(
            root,
            [(q["mode"], q["accepted"], q["pending"]) for q in results],
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    main(a.data, a.out)
