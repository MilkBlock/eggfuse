"""Measure a decoder on its own native snapshots; seal a Run only after iterator exhaustion."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryFile
from time import perf_counter

import torch

from cell_stream import CellStream
from recursive_rollout import EVAL, get_policy
from recursive_train import binary, folder, read
from relation_cases import request


@torch.no_grad()
def dynamic_wave(pol, frame):
    from recursive_agent import RUN_EXPANSIONS, RUN_PACKETS

    rd = pol.reader
    rd.advance(frame)
    rules = frame["rules"]
    run = frame["run"]
    features = [rd.rule_state(r, wm, run, pol.last_rule.get(r, 0)) for r, wm in rules]
    ranks = (
        pol.model.activation(torch.tensor(features, dtype=torch.float32).reshape(-1, 8))
        .flatten()
        .tolist()
    )
    expansions = 0
    batch = []
    for j in sorted(range(len(rules)), key=lambda j: -ranks[j]):
        r, wm = rules[j]
        stack = [((), pol.model.start(rd.meta(r)))]
        while stack and len(batch) < RUN_PACKETS:
            seq, h = stack.pop()
            if len(seq) == len(rd.order(r)):
                if seq or not wm or not rd.iface.rules[r]["metadata"]["seminaive"]:
                    batch.append(request(run, r, rd.addresses(r, seq), rd.store))
                continue
            if expansions >= RUN_EXPANSIONS:
                break
            expansions += 1
            dom, x = rd.read(r, seq, wm, 0)
            if dom:
                scores, z = pol.model(h, x)
                eligible = torch.where(scores >= 0)[0]
                ranked = eligible[
                    scores[eligible].argsort(descending=True, stable=True)
                ]
                for n in reversed(ranked.tolist()):
                    stack.append((seq + (dom[n],), z[n]))
    for q in batch:
        pol.last_rule[q["rule"]] = run
    return batch


@torch.no_grad()
def execute(
    root, case, arm, seconds, phase, limit=None, series="cell-stream", study=None
):
    d = folder(root, case)
    work = (
        root / series / (f"{case}-{arm}-{phase}" + (f"-first{limit}" if limit else ""))
    )
    work.mkdir(parents=True, exist_ok=True)
    pol = get_policy(root, d, "free", phase)
    rd = pol.reader
    schema = dict(
        schema="cell-token-replay/v2",
        program_sha256=hashlib.sha256((d / "program.json").read_bytes()).hexdigest(),
        repair_events=[],
    )
    accepted = []
    durable = 0
    trace = []
    costs = Counter()
    verdicts = Counter()
    end = None
    error = None
    current = None
    sealed = None
    paid = 0
    verify_ipc = 0.0
    start = perf_counter()
    deadline = start + seconds
    cmd = [binary(root), "online-waves", d / "program.json", "-", "audit", "--ept"]
    if limit is not None:
        cmd.insert(-1, str(limit))
    with (
        TemporaryFile(mode="w+") as err,
        subprocess.Popen(cmd, stdin=-1, stdout=-1, stderr=err, text=True) as proc,
    ):

        def send(batch, finish=False):
            nonlocal paid, verify_ipc
            tick = perf_counter()
            for q in batch:
                paid += 1
                q["token"] = paid
            header = json.dumps(dict(requests=batch, finish=finish)) + "\n"
            costs["json_encode_seconds"] += perf_counter() - tick
            costs["request_bytes"] += len(header)
            t = perf_counter()
            proc.stdin.write(header)
            proc.stdin.flush()
            costs["request_write_seconds"] += perf_counter() - t
            if batch:
                t = perf_counter()
                line = proc.stdout.readline()
                costs["receipt_read_seconds"] += perf_counter() - t
                costs["response_bytes"] += len(line)
                t = perf_counter()
                reply = json.loads(line)["verdicts"]
                for q, (token, v) in zip(batch, reply, strict=True):
                    assert q["token"] == token
                    verdicts[v] += 1
                    if v == "accepted":
                        accepted.append(q)
                if study is not None:
                    study.verdicts(batch, reply, rd)
                costs["receipt_decode_audit_seconds"] += perf_counter() - t
                costs["waves"] += 1
            else:
                costs["seals"] += 1
            verify_ipc += perf_counter() - tick

        try:
            for line in proc.stdout:
                f = json.loads(line)
                if sealed is not None:
                    sealed.update(elapsed=perf_counter() - start)
                    trace.append(sealed)
                    durable = sealed["accepted"]
                    sealed = None
                if "role" in f:
                    end = f
                    break
                schema["repair_events"].extend(f["repair_events"])
                current = f["run"]
                if perf_counter() > deadline:
                    raise TimeoutError
                batch = []
                if arm in ("fixed", "dynamic"):
                    batch = pol.issue(f) if arm == "fixed" else dynamic_wave(pol, f)
                    costs["visits"] = rd.count["visited"] + rd.count["bucket_visits"]
                else:
                    t = perf_counter()
                    rd.advance(f)
                    costs["memory_update_seconds"] += perf_counter() - t
                    for r, wm in f["rules"]:
                        st = (study.stream if study is not None else CellStream)(
                            rd, pol.model, r, wm, costs
                        )
                        for block in st.batches(arm, 0.0, deadline):
                            t = perf_counter()
                            prior_ipc = verify_ipc
                            for path in block:
                                batch.append(
                                    request(current, r, rd.addresses(r, path), rd.store)
                                )
                                if len(batch) == 256:
                                    send(batch)
                                    batch = []
                            costs["pack_seconds"] += (
                                perf_counter() - t - (verify_ipc - prior_ipc)
                            )
                if batch:
                    send(batch)
                sealed = dict(
                    run=current,
                    paid=paid,
                    accepted=len(accepted),
                    visits=costs["visits"],
                    interface_reads=costs["interface_reads"],
                    waves=costs["waves"],
                    replies=dict(verdicts),
                )
                send([], True)
        except TimeoutError:
            error = "wall_budget"
            proc.kill()
        finally:
            proc.stdin.close()
            proc.wait()
            err.seek(0)
            msg = err.read()
        if end is None and not error:
            if "source panic" not in msg:
                raise RuntimeError(msg)
            error = msg.strip()
    wall = perf_counter() - start
    costs["index_update_seconds"] = rd.count["index_update_seconds"]
    costs["index_writes"] = rd.index.writes
    costs["index_removes"] = rd.index.removes
    ref = read(d / "capture.json")
    if end is not None:
        schema["repair_events"] = end["runtime_events"]
    schema["requests"] = accepted[:durable]
    tape = work / "issued.json"
    tape.write_text(json.dumps(schema))
    replay = json.loads(
        subprocess.check_output(
            [
                binary(root),
                "replay",
                d / "program.json",
                tape,
                "audit",
                str(len(trace)),
                "--export",
                work / "state.json",
                "--ept",
            ]
        )
    )
    assert replay["runs"] == len(trace) and replay["counts"]["accepted"] == durable
    if end is not None:
        assert end["state_sha"] == replay["state_sha"]
    ops = sum(replay["ept"]["signed_external"]) + sum(replay["ept"]["signed_internal"])
    out = dict(
        case=case,
        arm=arm,
        phase=phase,
        runs=len(trace),
        last_run=current,
        termination=error or "schedule_end",
        exact_endpoint=end is not None and end["state_sha"] == ref["state_sha"],
        state_sha=replay["state_sha"],
        paid=paid,
        committed_tokens=durable,
        verdicts=dict(verdicts),
        work=dict(costs),
        wall=wall,
        verification_ipc=verify_ipc,
        guard_failures=end.get("guard_failures") if end else None,
        native_verify_seconds=end.get("verify_seconds") if end else None,
        signed_ops=ops,
        ept=ops / max(1, paid),
        eps=ops / wall,
        trace=trace,
    )
    (work / "metrics.json").write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("arm", choices=["dense", "stream", "fixed", "dynamic"])
    p.add_argument("cases", nargs="*")
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--phase", default="multi")
    p.add_argument("--limit", type=int)
    p.add_argument("--series", default="cell-stream")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases or EVAL:
        v = execute(
            a.root.resolve(),
            c,
            a.arm,
            a.seconds,
            a.phase,
            limit=a.limit,
            series=a.series,
        )
        print(
            c,
            a.arm,
            v["runs"],
            v["termination"][:24],
            v["paid"],
            v["work"].get("visits", 0),
            flush=True,
        )
