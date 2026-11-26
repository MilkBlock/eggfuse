"""Offline controlled timing and causal probes. No probe is available to online generation."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from ccp_v01 import Client, read_repairs
from cell_transaction import STATUS, memory_frame
from credit_scale_buffer import submit
from credit_scale_fit import load_shard
from discovery_score import token, write_csv


def probe(runtime, program, c, late):
    digest = hashlib.sha256(program.read_bytes()).hexdigest()
    with (
        tempfile.TemporaryDirectory() as tmp,
        tempfile.TemporaryFile() as err,
        subprocess.Popen(
            [runtime, "online-ccp-v0.1", program, "-", "audit", "2", "--ept"],
            stdin=-1,
            stdout=-1,
            stderr=err,
        ) as proc,
    ):
        client = Client(proc, 256, digest)
        receipts = []
        closed = False
        try:
            while line := proc.stdout.readline():
                f = json.loads(line)
                if "role" in f:
                    break
                memory_frame(proc.stdout, f)
                desc, _ = read_repairs(proc.stdout, f)
                if len(desc):
                    raise ValueError("unexpected repair in simple relation probe")
                if f.get("final_publication"):
                    continue
                r = client.run = f["run"]
                client.epoch = f["epoch"]
                if (late and r == 2) or (not late and r == 1):
                    if late and c.rule not in dict(f["rules"]):
                        closed = True
                    else:
                        receipts = submit(client, [c] if late else [c, c], 256)
                client.seal()
            proc.stdin.close()
            if proc.wait():
                err.seek(0)
                raise ValueError(err.read().decode()[-1000:])
            tape = Path(tmp) / "issued.json"
            tape.write_text(
                json.dumps(
                    {
                        "schema": "cell-token-replay/v2",
                        "program_sha256": digest,
                        "repair_events": [],
                        "requests": list(client.offline_tape(2)),
                    }
                )
            )
            cmd = [runtime, "replay", program, tape, "audit", "1"]
            nxt = json.loads(subprocess.check_output([*cmd, "--audit-next-proofs"]))
            report = json.loads(subprocess.check_output([*cmd, "--ept-origins"]))
            return (
                (
                    ["closed_schedule_no_issue"]
                    if closed
                    else [STATUS[x[1]] for x in receipts]
                ),
                dict(report["ept"]["origins"]),
                nxt,
            )
        finally:
            if proc.poll() is None:
                proc.kill()
            client.close()


def main(a):
    rows = []
    paths = sorted((a.out / "buffer").glob("*-2-*.json.gz"))
    for file in paths[:: max(1, len(paths) // a.count)][: a.count]:
        sh = load_shard(file)
        first = sh["events"][0]
        q = next(
            (
                token(c)
                for c, v in zip(first["generated"], first["signed_gain"], strict=True)
                if v
            ),
            None,
        )
        if not q:
            continue
        d = a.previous / "programs" / f"{sh['idx']:04d}"
        if not d.is_dir():
            d = a.out / "novel" / "programs" / f"{sh['idx']:04d}"
        early, g, nxt = probe(a.runtime, d / "program.json", q, False)
        late, lg, without = probe(a.runtime, d / "program.json", q, True)
        assert (
            early == ["accepted", "duplicate"] and g.get(1, 0) > 0 and not lg.get(1, 0)
        )
        enabled = [
            k for k in nxt if any(v["address"]["token"] == 1 for v in k["parents"])
        ]
        rows.append(
            {
                "program": sh["idx"],
                "token": json.dumps([q.rule, q.refs]),
                "on_time": early[0],
                "repeated": early[1],
                "delayed": late[0],
                "effective": g[1],
                "enabled": len(enabled),
                "without_bindings": len(without),
                "with_bindings": len(nxt),
            }
        )
    write_csv(a.out / "controlled-timing.csv", rows)
    print(
        len(rows), "paired forks", sum(r["enabled"] for r in rows), "dependent bindings"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("runtime", "previous", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--count", type=int, default=32)
    main(p.parse_args())
