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
):
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
    cmd = [
        binary(root),
        "online-transactions",
        d / "program.json",
        "-",
        "audit",
        "--ept",
    ]
    if limit is not None:
        cmd.insert(-1, str(limit))
    trace = []
    repairs = []
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
                    trace.append(dict(**sealed, elapsed=perf_counter() - start))
                    sealed = None
                if "role" in frame:
                    end = frame
                    break
                txn.run = current = frame["run"]
                repairs.extend(frame["repair_events"])
                if perf_counter() >= deadline:
                    raise TimeoutError
                t = perf_counter()
                publication = memory_frame(proc.stdout, frame)
                stats["boundary_decode_seconds"] += perf_counter() - t
                t = perf_counter()
                update_memory(rd, frame, publication)
                stats["memory_update_seconds"] += perf_counter() - t
                for rule, wm in frame["rules"]:
                    if perf_counter() >= deadline:
                        raise TimeoutError
                    stream = study.stream(rd, pol.model, rule, wm, stats)
                    stream.transaction = txn
                    for paths in stream.path_batches("stream", 0.0, deadline):
                        txn.proofs_from_paths(stream, paths)
                txn.seal()
                sealed = dict(
                    run=current,
                    paid=txn.paid,
                    accepted=txn.verdicts["accepted"],
                    visits=stats["visits"],
                    interface_reads=stats["interface_reads"],
                    waves=sum(txn.sizes.values()),
                    replies=dict(txn.verdicts),
                )
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
            stderr.seek(0)
            msg = stderr.read().decode()
        if end is None and error is None:
            if "source panic" not in msg:
                raise RuntimeError(
                    f"native binary stream terminated without a report: {msg}"
                )
            error = msg.strip()
    wall = perf_counter() - start
    ref = read(d / "capture.json")
    tape = work / "issued.json"
    schema = dict(
        schema="cell-token-replay/v2",
        program_sha256=hashlib.sha256((d / "program.json").read_bytes()).hexdigest(),
        requests=list(txn.offline_tape(len(trace))),
        repair_events=end["runtime_events"] if end else repairs,
    )
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
    out = dict(
        case=case,
        arm="stream",
        phase="multi",
        runs=len(trace),
        last_run=current,
        termination=error or "schedule_end",
        exact_endpoint=end is not None and replay["state_sha"] == ref["state_sha"],
        state_sha=replay["state_sha"],
        paid=txn.paid,
        proof_paid=txn.proofs,
        compute_paid=txn.computations,
        committed_tokens=len(schema["requests"]),
        verdicts=dict(txn.verdicts),
        work=dict(stats),
        transaction_sizes=dict(txn.sizes),
        synchronizations=sum(txn.sizes.values()) + txn.costs["seals"],
        txn_stats=end.get("txn_stats") if end else None,
        trace=trace,
        wall=wall,
        signed_ops=ops,
        ept=ops / max(1, txn.paid),
        eps=ops / wall,
        native_verify_seconds=end.get("verify_seconds") if end else None,
        guard_failures=end.get("guard_failures") if end else None,
    )
    (work / "metrics.json").write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("case")
    parser.add_argument("--series", default="transaction-buffer")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seconds", type=float, default=60)
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
