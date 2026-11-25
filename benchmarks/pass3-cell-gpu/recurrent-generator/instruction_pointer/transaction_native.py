"""Independent CPU Cell Stream rollout over native typed transactions."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryFile
from time import perf_counter

import torch

from ccp_v01 import Client, offline_repairs, read_repairs
from cell_transaction import Transaction, memory_frame, update_memory
from recursive_rollout import get_policy
from recursive_train import binary, folder, read
from stream_guard import Study


@torch.no_grad()
def execute(
    root,
    case,
    study=None,
    seconds=60,
    series="transaction-buffer",
    limit=None,
    capacity=256,
    protocol="ccp-v0.1",
):
    init = perf_counter()
    root = Path(root).resolve()
    d = folder(root, case)
    work = (
        root / series / (f"{case}-stream-multi" + (f"-first{limit}" if limit else ""))
    )
    work.mkdir(parents=True, exist_ok=True)
    pol = get_policy(root, d, "free", "multi")
    rd = pol.reader
    if study is None:
        study = Study(bits=8, symmetric=True)
    mode = {"ccp-v0.1": "online-ccp-v0.1", "ctx1": "online-transactions"}[protocol]
    cmd = [
        binary(root),
        mode,
        d / "program.json",
        "-",
        "audit",
        "--ept",
    ]
    if limit is not None:
        cmd.insert(-1, str(limit))
    trace = []
    repairs = []
    repair_blocks = []
    committed = 0
    stats = Counter()
    sealed = None
    end = None
    error = None
    current = None
    start = perf_counter()
    deadline = start + seconds
    with (
        TemporaryFile() as stderr,
        subprocess.Popen(cmd, stdin=-1, stdout=-1, stderr=stderr) as proc,
    ):
        if protocol == "ccp-v0.1":
            digest = hashlib.sha256((d / "program.json").read_bytes()).hexdigest()
            txn = getattr(study, "client_type", Client)(proc, capacity, digest)
        else:
            txn = Transaction(proc, capacity)
        try:
            while True:
                boundary = perf_counter()
                line = proc.stdout.readline()
                stats["boundary_wait_seconds"] += perf_counter() - boundary
                if not line:
                    break
                t = perf_counter()
                frame = json.loads(line)
                stats["header_decode_seconds"] += perf_counter() - t
                if sealed is not None:
                    committed = sealed["run"]
                if (
                    protocol == "ccp-v0.1"
                    and frame.get("committed_through_run") != committed
                ):
                    raise RuntimeError(
                        "CCP publication did not acknowledge the expected sealed Run"
                    )
                acknowledged = sealed is not None
                if acknowledged:
                    trace.append(dict(**sealed, elapsed=perf_counter() - start))
                    sealed = None
                if "role" in frame:
                    end = frame
                    break
                txn.run = current = frame["run"]
                txn.epoch = frame["epoch"]
                if protocol == "ctx1":
                    repairs.extend(frame["repair_events"])
                t = perf_counter()
                publication = memory_frame(proc.stdout, frame)
                repair_types = None
                if protocol == "ccp-v0.1":
                    desc, ops = read_repairs(proc.stdout, frame)
                    if len(desc):
                        repair_blocks.append((desc, ops))
                    repair_types = zip(desc[:, 0], desc[:, 2])
                stats["boundary_decode_seconds"] += perf_counter() - t
                t = perf_counter()
                update_memory(rd, frame, publication, repair_types)
                stats["memory_update_seconds"] += perf_counter() - t
                if acknowledged:
                    trace[-1]["elapsed"] = perf_counter() - start
                if frame.get("final_publication"):
                    current = committed
                    continue
                if perf_counter() >= deadline:
                    raise TimeoutError
                if hasattr(study, "run_snapshot"):
                    study.run_snapshot(
                        frame, publication, rd, pol.model, txn, stats, deadline
                    )
                else:
                    for rule, wm in frame["rules"]:
                        if perf_counter() >= deadline:
                            raise TimeoutError
                        stream = study.stream(rd, pol.model, rule, wm, stats)
                        stream.transaction = txn
                        for paths in stream.path_batches("stream", 0.0, deadline):
                            txn.proofs_from_paths(stream, paths)
                txn.seal()
                sealed = {
                    "run": current,
                    "paid": txn.paid,
                    "accepted": txn.verdicts["accepted"],
                    "visits": stats["visits"],
                    "interface_reads": stats["interface_reads"],
                    "waves": sum(txn.sizes.values()),
                    "controls": stats["neural_controls"],
                    "replies": dict(txn.verdicts),
                }
        except TimeoutError:
            proc.kill()
            error = "wall_budget"
        except (EOFError, BrokenPipeError):
            # A native source assertion may terminate the child mid-batch.
            if proc.poll() is None:
                proc.stdin.close()
        finally:
            if end is None and error is None and proc.poll() is None:
                proc.kill()
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            proc.wait()
            if protocol == "ccp-v0.1":
                txn.close()
            stderr.seek(0)
            msg = stderr.read().decode()
        if end is None and error is None:
            if "source panic" not in msg:
                raise RuntimeError(
                    f"native binary stream terminated without a report: {msg}"
                )
            error = msg.strip()
    wall = perf_counter() - start
    if end is not None and trace:
        trace[-1]["elapsed"] = wall
    ref = read(d / "capture.json")
    tape = work / "issued.json"
    schema = {
        "schema": "cell-token-replay/v2",
        "program_sha256": hashlib.sha256((d / "program.json").read_bytes()).hexdigest(),
        "requests": list(txn.offline_tape(len(trace))),
        "repair_events": list(offline_repairs(repair_blocks))
        if protocol == "ccp-v0.1"
        else (end["runtime_events"] if end else repairs),
    }
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
    assert replay["counts"]["accepted"] == len(schema["requests"]) and replay[
        "runs"
    ] == len(trace)
    if end is not None:
        assert (
            replay["state_sha"] == end["state_sha"]
            and sum(txn.verdicts.values()) == txn.paid
        )
    ops = sum(replay["ept"]["signed_external"]) + sum(replay["ept"]["signed_internal"])
    stats.update(txn.costs)
    stats.update(
        index_update_seconds=rd.count["index_update_seconds"],
        index_writes=rd.index.writes,
        index_removes=rd.index.removes,
    )
    out = {
        "case": case,
        "arm": "stream",
        "phase": "multi",
        "runs": len(trace),
        "last_run": current,
        "termination": error or "schedule_end",
        "exact_endpoint": end is not None and replay["state_sha"] == ref["state_sha"],
        "state_sha": replay["state_sha"],
        "paid": txn.paid,
        "proof_paid": txn.proofs,
        "compute_paid": txn.computations,
        "committed_tokens": len(schema["requests"]),
        "verdicts": dict(txn.verdicts),
        "work": dict(stats),
        "transaction_sizes": dict(txn.sizes),
        "synchronizations": (
            txn.costs["collection_barriers"]
            if protocol == "ccp-v0.1"
            else sum(txn.sizes.values())
        )
        + txn.costs["seals"],
        "protocol": protocol,
        "txn_stats": end.get("txn_stats") if end else None,
        "trace": trace,
        "wall": wall,
        "runtime_setup_seconds": start - init,
        "signed_ops": ops,
        "ept": ops / max(1, txn.paid),
        "eps": ops / wall,
        "native_verify_seconds": end.get("verify_seconds") if end else None,
        "guard_failures": end.get("guard_failures") if end else None,
    }
    (work / "metrics.json").write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("case")
    parser.add_argument("--series", default="transaction-buffer")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--protocol", choices=["ctx1", "ccp-v0.1"], default="ccp-v0.1")
    parser.add_argument("--capacity", type=int, default=256)
    a = parser.parse_args()
    torch.set_num_threads(1)
    print(
        {
            k: v
            for k, v in execute(**vars(a)).items()
            if k not in ("trace", "guard_failures")
        }
    )
