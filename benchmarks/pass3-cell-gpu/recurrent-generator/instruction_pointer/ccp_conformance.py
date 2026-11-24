"""Independent wire checks against the native runtime, using a captured CYK fixture."""

import argparse
import hashlib
import itertools
import json
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

from ccp_v01 import Client, offline_repairs, read_repairs
from cell_transaction import STATUS, memory_frame


def read_refs(req):
    return [
        [p["address"]["token"], p["address"]["op"], p["version"], -1]
        for p in req["parents"]
    ]


def run(binary, corpus):
    program = corpus / "program.json"
    digest = hashlib.sha256(program.read_bytes()).hexdigest()
    recipe = json.loads(program.read_bytes())["recipe"]
    proof = json.loads((corpus / "tape.json").read_bytes())["requests"][0]
    cmd = [binary, "online-ccp-v0.1", program, "-", "audit", "2", "--ept"]
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        client = Client(proc, 16, digest)
        try:
            f = json.loads(proc.stdout.readline())
            assert f["committed_through_run"] == 0 and proof["run"] == f["run"]
            client.run, client.epoch = f["run"], f["epoch"]
            memory_frame(proc.stdout, f)
            read_repairs(proc.stdout, f)
            rid = proof["rule"]
            parents = read_refs(proof)
            table = next(
                i
                for i, a in enumerate(recipe["rules"][rid]["query"])
                if a["call"].get("table") == "getString"
            )
            addr = parents[table][:3]
            # A model chooses all descriptors and observation masks. Here fixture
            # references exercise the ABI only, outside the policy measurement.
            plus_rule, pc = next(
                (r, i)
                for r, _ in f["rules"]
                for i, a in enumerate(recipe["rules"][r]["query"])
                if a["call"].get("primitive") == "+"
                and all("slot" in x for x in a["args"][:2])
            )
            local = [0, 0, 0, 0]
            refs = [
                [*addr, 0],
                local,
                local,
                local,
                local,
                [0, 5, 0, 0],
                local,
                [*addr[:2], addr[2] + 1, 0],
                [*addr, 1],
            ]
            ops = [
                [2, 0, rid, -1, 1],
                [1, 0, plus_rule, pc, 3],
                [1, 0, plus_rule, pc, 5],
                [1, 0, plus_rule, pc, 7],
                [2, 0, rid, -1, 8],
                [2, 0, rid, -1, 9],
            ]
            calc = client.enqueue(ops, refs, [3, 2, 0, 2, 2, 2])
            accepted = client.enqueue([[0, 0, rid, -1, len(parents)]], parents, 0)
            owner = int(accepted.op[0, 1])
            pending = client.enqueue([[2, 0, rid, -1, 1]], [[owner, 1, 0, 0]], 2)
            assert client.collect(pending).rows[0, 1] == STATUS.index("pending_port")
            assert client.collect(accepted).rows[0, 1] == STATUS.index("accepted")
            result = client.collect(calc)
            assert result.rows[:, 1].tolist() == [14, 14, 14, 15, 8, 14]
            assert result.rows[1:, 3].count_nonzero() == 0
            ends = [0, *result.value_ends.tolist()]
            data = [result.values[a:b].tobytes() for a, b in itertools.pairwise(ends)]
            assert data[0][0] == data[1][0] == 1
            value = struct.unpack_from("<q", data[0], 1)[0]
            assert data[1] == struct.pack("<Bq", 1, 2 * value)
            assert data[2:5] == [b""] * 3 and data[5][0] == 3
            assert struct.unpack_from("<Q", data[5], 1)[0] == len(
                data[5][9:].decode().encode()
            )
            client.seal()
            f = json.loads(proc.stdout.readline())
            assert f["committed_through_run"] == 1
            rows, _, _, ids = memory_frame(proc.stdout, f)
            read_repairs(proc.stdout, f)
            assert [owner, rid] in ids.tolist()
            row = next(x for x in rows if x[0] == owner and x[1] == 1)
            client.run, client.epoch = f["run"], f["epoch"]
            assert (
                client.collect(
                    client.enqueue([[2, 0, rid, -1, 1]], [[owner, 1, row[3], 0]], 2)
                ).rows[0, 1]
                == 14
            )
            client.seal()
            final = json.loads(proc.stdout.readline())
            assert final["final_publication"] and final["committed_through_run"] == 2
            memory_frame(proc.stdout, final)
            read_repairs(proc.stdout, final)
            end = json.loads(proc.stdout.readline())
            assert (
                end["committed_through_run"] == 2
                and end["txn_stats"]["cache_hits"] == 1
            )
            assert end["txn_stats"]["request_bytes"] == client.costs["request_bytes"]
            assert end["txn_stats"]["response_bytes"] == client.costs["response_bytes"]
        finally:
            proc.stdin.close()
            client.close()
        assert proc.wait() == 0
    # Bad version, replayed ID, wrong Run and wrong graph epoch must all fail before body decode.
    for version, seq, run_delta, epoch_delta in [
        (2, 1, 0, 0),
        (1, 0, 0, 0),
        (1, 1, 1, 0),
        (1, 1, 0, 1),
    ]:
        with subprocess.Popen(cmd, stdin=-1, stdout=-1, stderr=-1) as proc:
            assert json.loads(proc.stdout.readline())["program_sha256"] == digest
            f = json.loads(proc.stdout.readline())
            memory_frame(proc.stdout, f)
            read_repairs(proc.stdout, f)
            _, err = proc.communicate(
                struct.pack(
                    "<4sHHQQQ",
                    b"CCPQ",
                    0,
                    version,
                    seq,
                    f["run"] + run_delta,
                    f["epoch"] + epoch_delta,
                )
            )
            assert proc.returncode and b"mismatch" in err
    print("CCP/0.1 native conformance passed")


def replay(binary, corpus, limit=None):
    program = corpus / "program.json"
    tape = json.loads((corpus / "tape.json").read_bytes())
    teacher = json.loads((corpus / "capture.json").read_bytes())
    by_run = defaultdict(list)
    for req in tape["requests"]:
        by_run[req["run"]].append(req)
    cmd = [binary, "online-ccp-v0.1", program, "-", "audit"]
    if limit is not None:
        cmd.append(str(limit))
    cmd.append("--ept")
    events = []
    published = set()
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        client = Client(proc, 65536, tape["program_sha256"])
        try:
            while True:
                f = json.loads(proc.stdout.readline())
                if "role" in f:
                    break
                _, _, _, accepted = memory_frame(proc.stdout, f)
                published.update(accepted[:, 0].tolist())
                events.extend(offline_repairs([read_repairs(proc.stdout, f)]))
                if f["final_publication"]:
                    break
                client.run, client.epoch = f["run"], f["epoch"]
                ops, refs = [], []
                for req in by_run[f["run"]]:
                    assert req["token"] == client.paid + len(ops) + 1
                    refs.extend(read_refs(req))
                    ops.append([0, 0, req["rule"], -1, len(refs)])
                if ops:
                    import numpy as np

                    receipt = client.collect(
                        client.enqueue(
                            ops, np.asarray(refs, dtype="<i8").reshape(-1, 4), 0
                        )
                    )
                    assert receipt.rows[:, 1].count_nonzero() == 0
                client.seal()
            assert f["final_publication"]
            end = json.loads(proc.stdout.readline())
            assert end["committed_through_run"] == f["committed_through_run"]
            expected = {q["token"] for q in tape["requests"] if q["run"] <= end["runs"]}
            assert published == expected
            assert events == [
                e for e in tape["repair_events"] if e["run"] <= end["runs"]
            ]
            if limit is None:
                for k in ("schedule", "state_sha", "writes", "rhs"):
                    assert end[k] == teacher[k], k
            print(
                corpus.name,
                "published owners",
                len(published),
                "repair events",
                len(events),
            )
        finally:
            proc.stdin.close()
            client.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("binary", type=Path)
    p.add_argument("corpus", type=Path)
    p.add_argument("--repair-corpus", type=Path)
    a = p.parse_args()
    run(a.binary, a.corpus)
    replay(a.binary, a.corpus, 1)
    if a.repair_corpus:
        replay(a.binary, a.repair_corpus)
