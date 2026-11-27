"""Fixed-exit independent CCP v0.1 runs on held pure equality programs."""

import hashlib
import json
import os
import random
import subprocess
from time import perf_counter
import numpy as np
import torch
from binding_model import Decoder, parser, tensor, collate
from binding_packets import public_view
from ccp_v01 import Client, read_repairs
from cell_transaction import memory_frame
from completion_context import native, read, write
from credit_scale_buffer import submit
from discrete_draft import Cell
from discovery_sampling import Domain
from query_environment import conditioned


@torch.no_grad()
def trial(a, d, arm, net, seed, *, generate=None, address_seed=None):
    ir = d / "program.json"
    digest = hashlib.sha256(ir.read_bytes()).hexdigest()
    observer = a.out / f"live-{seed}.jsonl"
    t = perf_counter()
    program = read(ir)
    m = conditioned(a, d, observer)
    rng = np.random.default_rng(seed)
    paid = 0
    command = [a.runtime_binary, "online-ccp-v0.1", ir, "-", "audit", "--ept"]
    if address_seed is not None:
        command.extend(["--address-seed", str(address_seed)])
    with subprocess.Popen(
        command,
        stdin=-1,
        stdout=-1,
        env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(observer)),
    ) as proc:
        client = Client(proc, 64, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                rows, hashes, retired, accepted = memory_frame(proc.stdout, f)
                read_repairs(proc.stdout, f)
                if f.get("final_publication"):
                    continue
                updates = []
                offset = 0
                for uid, op, table, ver, fw, end in rows.tolist():
                    updates.append(
                        [
                            dict(token=uid, op=op),
                            dict(
                                table=table,
                                version=ver,
                                forwarded=bool(fw),
                                hashes=hashes[offset:end].tolist(),
                            ),
                        ]
                    )
                    offset = end
                f.update(
                    updates=updates,
                    accepted=accepted.tolist(),
                    retired=[dict(token=int(t), op=int(o)) for t, o in retired],
                )
                m.update(f)
                client.run = f["run"]
                client.epoch = f["epoch"]
                if m.ids:
                    if generate is not None:
                        paid += generate(client, public_view(m, program), program, rng)
                        client.seal()
                        continue
                    if arm == "random":
                        cells = list(
                            Domain(m).draw("factored", random.Random(seed), 32)
                        )
                    else:
                        z = public_view(m, program)
                        u = tensor(
                            rng.random((1, 32, len(z["banks"]))).astype(np.float32)
                        )
                        _, sel = net(collate([z]), draws=32, noise=u)
                        cells = [
                            Cell(
                                z["rule"],
                                tuple(z["addrs"][j][idx] for j, idx in enumerate(ix)),
                            )
                            for ix in sel[0].cpu().tolist()
                        ]
                    submit(client, cells, 32)
                    paid += len(cells)
                client.seal()
            if proc.wait() != 0 or "role" not in f:
                raise RuntimeError("native session incomplete")
        finally:
            client.close()
            m.close_observer()
    wall = perf_counter() - t
    ops = sum(f["ept"]["signed_external"]) + sum(f["ept"]["signed_internal"])
    return dict(
        arm=arm,
        seed=seed,
        size=int(d.name.split("-", 1)[0]),
        paid=paid,
        ops=ops,
        seconds=wall,
        eps=ops / wall,
        ept=ops / max(1, paid),
        graph=f["state_sha"],
        receipts=f["counts"],
    )


if __name__ == "__main__":
    a = parser().parse_args()
    torch.set_num_threads(1)
    results = []
    for seed in a.seeds:
        models = {}
        for arm in a.arms:
            net = Decoder(a, arm).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            models[arm] = net
        for n in (4, 16, 64, 256, 1024):
            d = a.out / "worlds/test" / f"{n:04}-eq10-20000-0"
            # Reference collection remains outside timed generation.
            ref = read(d / "ok.json")
            goal = len(ref["gold"])
            reference = native(a, d, "capture", a.out / "online-ref.json")["state_sha"]
            for block in (0, 1):
                arms = ["random", *a.arms]
                for arm in arms if not block else arms[::-1]:
                    row = trial(a, d, arm, models.get(arm), seed)
                    row.update(block=block, reference=goal, coverage=row["ops"] / goal)
                    row["matches_reference"] = row["graph"] == reference
                    assert 0 <= row["ops"] <= goal and row["matches_reference"] == (
                        row["ops"] == goal
                    )
                    results.append(row)
            print(seed, n, flush=True)
    write(a.out / "online.json", results)
