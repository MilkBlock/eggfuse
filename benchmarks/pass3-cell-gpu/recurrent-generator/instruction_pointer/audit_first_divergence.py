"""Check the first divergent native Run of the unbudgeted symbolic one/two-owner arm."""

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from anchor_set_audit import check
from higher_cell import read
from join_controls import Generator
from relation_cases import request


def identity(q):
    return tuple(
        (a["address"]["token"], a["address"]["op"], a["version"]) for a in q["parents"]
    )


def online_prefix(folder, binary, program, stop):
    gen = Generator(folder.parent, program, "A")
    seq = 0
    with subprocess.Popen(
        [binary, "online", folder / "program.json", "-", "audit", str(stop)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    ) as proc:
        for line in proc.stdout:
            f = json.loads(line)
            if "role" in f:
                break
            gen.advance(f)
            rows = [
                q for ps in gen.issue(f, bootstrap=True, live=True).values() for q in ps
            ]
            for q in rows:
                seq += 1
                q["token"] = seq
            proc.stdin.write(json.dumps(rows) + "\n")
            proc.stdin.flush()
        proc.stdin.close()
        assert proc.wait() == 0 and f["role"] == "online"
    return f


def diagnose(root, case):
    folder = root / case
    binary = root / "whole-fork-credit/receiver"
    ref = read(folder / "capture.json")
    n = (
        read(root / "track-diagnostic" / f"{case}-exclusive.json")["arms"]["A"][
            "exact_common_runs"
        ]
        + 1
    )
    tape = read(folder / "tape.json")
    program = read(folder / "program.json")

    def exact_prefix(r):
        return json.loads(
            subprocess.check_output(
                [binary, "reference", folder / "program.json", "-", "audit", str(r)]
            )
        )

    before = online_prefix(folder, binary, program, n - 1)
    gold = exact_prefix(n - 1)
    for k in ("state_sha", "rhs", "writes", "events", "schedule"):
        assert before[k] == gold[k], (case, k)
    after = online_prefix(folder, binary, program, n)
    expected = exact_prefix(n)
    targets = {p["token"]: p for p in tape["requests"] if p["run"] == n}
    gen = Generator(root, program, "A")
    for line in (folder / "memory.jsonl").open():
        f = json.loads(line)
        gen.advance(f)
        if f["run"] == n:
            break
    assert gen.store.visible and f["run"] == n
    offers = [q for block in gen.issue(f, bootstrap=True).values() for q in block]

    def verify(rows):
        for i, q in enumerate(rows, 1):
            q["token"] = i
        verdicts = check(folder, binary, tape, rows)["recall_verdicts"]
        return [(rows[token - 1], w) for _, token, w, _ in verdicts if w is not None]

    actual = verify(offers)
    missing = targets.keys() - {w for _, w in actual}
    assert len(targets) - len(missing) == after["schedule"][-1][4]
    # Full finite address product for every missed rule. Include stale delta choices:
    # native evaluation checks versions, watermark, values, guards and winner identity.
    trials = []
    for rid in sorted({targets[t]["rule"] for t in missing}):
        pools = [
            [
                key
                for key, row in gen.store.visible.items()
                if row["table"] == gen.store.iface.tables.index(table)
            ]
            for table, _ in gen.store.iface.roles[rid]
        ]
        trials.extend(request(n, rid, keys, gen.store) for keys in product(*pools))
    proofs = defaultdict(list)
    for q, w in verify(trials):
        proofs[w].append(identity(q))
    # Intervene only on the missing bindings in the otherwise exact teacher prefix.
    with TemporaryDirectory() as tmp:
        stripped = Path(tmp) / "without.json"
        stripped.write_text(
            json.dumps(
                {
                    **tape,
                    "requests": [
                        p
                        for p in tape["requests"]
                        if p["run"] <= n and p["token"] not in missing
                    ],
                }
            )
        )
        fork = json.loads(
            subprocess.check_output(
                [binary, "replay", folder / "program.json", stripped, "audit", str(n)]
            )
        )
    same = {
        k: fork[k] == after[k]
        for k in ("schedule", "writes", "rhs", "events", "state_sha")
    }
    assert all(same.values()), (case, same)
    counts = Counter(direct=0, transitive=0)
    impacted = set(missing)
    for q in tape["requests"]:
        if q["run"] <= n:
            continue
        ps = {a["address"]["token"] for a in q["parents"]}
        if ps & missing:
            counts["direct"] += 1
        if ps & impacted:
            counts["transitive"] += 1
            impacted.add(q["token"])
    absent = []
    offerids = {(q["rule"], identity(q)) for q in offers}
    for t in sorted(missing):
        teacher = targets[t]
        ids = identity(teacher)
        choices = proofs[t]
        assert ids in choices
        absent.append(
            dict(
                token=t,
                rule=teacher["rule"],
                parents=ids,
                owners=len({x[0] for x in ids}),
                in_A=(teacher["rule"], ids) in offerids,
                proofs=len(choices),
                minimum_owners=min(len({x[0] for x in option}) for option in choices),
                alternative_proofs=sum(option != ids for option in choices),
            )
        )
    return dict(
        run=n,
        ruleset=ref["schedule"][n - 1][0],
        before_sha=before["state_sha"],
        reference_sha=expected["state_sha"],
        arm_sha=after["state_sha"],
        all_A_requests=len(offers),
        teacher=len(targets),
        hit=len(targets) - len(missing),
        missing=absent,
        typed_proofs_checked=len(trials),
        omission_fork_equal=same,
        recorded_descendants=counts,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    a.output.write_text(
        json.dumps(
            {
                c: diagnose(a.root.resolve(), c)
                for c in ("fact", "loopfact", "sum-divisors")
            },
            indent=2,
        )
        + "\n"
    )
