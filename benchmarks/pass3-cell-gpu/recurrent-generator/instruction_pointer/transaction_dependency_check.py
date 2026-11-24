"""Replay a captured CYK grammar and exercise the native transaction-local scalar ABI.

The oracle tape is used only by this protocol regression. No exact lookup or
teacher input is available to the deployed generator.
"""

import argparse
import json
import struct
import subprocess
from collections import defaultdict
from pathlib import Path

from cell_transaction import MAGIC, STATUS, read_matrix


def send(proc, operations, refs, finish=False):
    proc.stdin.write(struct.pack("<4I", MAGIC, len(operations), len(refs), finish))
    for op in operations:
        proc.stdin.write(struct.pack("<5q", *op))
    for ref in refs:
        proc.stdin.write(struct.pack("<4q", *ref))
    proc.stdin.flush()
    return read_matrix(proc.stdout, len(operations), 4)


def field(p, col):
    return [p["address"]["token"], p["address"]["op"], p["version"], col]


def probe(proc, program, request, fields, base):
    # Locate a binary CYK adjacency primitive. Its two inputs must have a table
    # witness before it, and its output must bind a field in a later premise.
    rid = request["rule"]
    query = program["recipe"]["rules"][rid]["query"]
    parents = iter(request["parents"])
    atoms = [(i, a, next(parents)) for i, a in enumerate(query) if "table" in a["call"]]
    for pc, atom in enumerate(query):
        if atom["call"].get("primitive") != "+" or len(atom["args"]) != 3:
            continue
        before = {
            arg["slot"]: field(p, c)
            for i, a, p in atoms
            if i < pc
            for c, arg in enumerate(a["args"])
            if "slot" in arg
        }
        after = {
            arg["slot"]: field(p, c)
            for i, a, p in atoms
            if i > pc
            for c, arg in enumerate(a["args"])
            if "slot" in arg
        }
        a, b, result = [arg.get("slot") for arg in atom["args"]]
        if a not in before or b not in before or result not in after:
            continue
        left, length, right = before[a], before[b], after[result]
        # Replacing left.start with right.start is type- and role-compatible
        # for the CYK fixture's same-table span facts. This is an independent
        # direct computation to compare with the transaction-local dependency.
        if (
            left[3] != right[3]
            or fields[tuple(left[:2])][0] != fields[tuple(right[:2])][0]
        ):
            continue
        direct = [0, 0, 0, 0]
        forward = [0, 4, 0, 0]
        rejected = [0, 2, 0, 0]
        stale = [left[0], left[1], left[2] + 1, left[3]]
        refs = [
            left,
            length,
            direct,
            length,
            forward,
            length,
            rejected,
            length,
            stale,
            length,
            right,
            length,
        ]
        ops = [[1, base + i, rid, pc, (i + 1) * 2] for i in range(6)]
        reply = send(proc, ops, refs)
        assert [STATUS[i] for i in reply[:, 1]] == [
            "computed",
            "computed",
            "bad_dependency",
            "bad_dependency",
            "version",
            "computed",
        ]
        assert list(reply[:, 0]) == list(range(base, base + 6)) and all(
            reply[:, 2] == pc
        )
        assert int(reply[0, 3]) % (1 << 64) == fields[tuple(right[:2])][1][right[3]]
        assert reply[1, 3] == reply[5, 3]
        return True
    return False


def check(binary, corpus):
    program = json.loads((corpus / "program.json").read_bytes())
    teacher = json.loads((corpus / "capture.json").read_bytes())
    requests = json.loads((corpus / "tape.json").read_bytes())["requests"]
    per_run = defaultdict(list)
    for request in requests:
        per_run[request["run"]].append(request)
    base = max(q["token"] for q in requests) + 1
    tested = False
    fields = {}
    cmd = [
        binary,
        "online-transactions",
        corpus / "program.json",
        "-",
        "audit",
        "--ept",
    ]
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        try:
            while True:
                f = json.loads(proc.stdout.readline())
                if "role" in f:
                    break
                rows = read_matrix(proc.stdout, f["typed_rows"], 6)
                hashes = read_matrix(proc.stdout, f["typed_hashes"], 1, "<u8").ravel()
                retired = read_matrix(proc.stdout, f["typed_retired"], 2)
                read_matrix(proc.stdout, f["typed_accepted"], 2)
                start = 0
                for token, op, table, _, _, end in rows:
                    fields[token, op] = int(table), hashes[start:end]
                    start = end
                for addr in retired:
                    del fields[tuple(addr)]
                ops = []
                refs = []
                for req in per_run[f["run"]]:
                    if not tested:
                        tested = probe(proc, program, req, fields, base)
                    refs.extend(field(p, -1) for p in req["parents"])
                    ops.append([0, req["token"], req["rule"], -1, len(refs)])
                if ops:
                    assert all(send(proc, ops, refs)[:, 1] == STATUS.index("accepted"))
                send(proc, [], [], True)
        finally:
            proc.stdin.close()
        assert proc.wait() == 0
    assert tested, "use a CYK fixture with binary span witnesses"
    for k in ("state_sha", "rhs", "schedule", "writes"):
        assert f[k] == teacher[k], k
    assert f["txn_stats"]["computed"] == 3
    return {
        "proofs": len(requests),
        "state_sha": f["state_sha"],
        "txn_stats": f["txn_stats"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("binary", type=Path)
    p.add_argument("corpus", type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.binary, args.corpus), indent=2))
