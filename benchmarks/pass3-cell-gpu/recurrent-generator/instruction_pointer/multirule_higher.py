"""Given-Higher interface ablation: two imports, one shared column, eight jobs at every size."""

import hashlib
import json
import os
import subprocess
from time import perf_counter

import numpy as np
import torch

from binding_egg import unpack
from binding_packets import public_view
from ccp_v01 import Client
from completion_context import read
from credit_scale_buffer import submit
from discrete_cells import load_enc
from discrete_draft import Cell
from first_parent import records
from head_joint_index import draw
from head_joint_index import prepare as index
from partner_index import noise
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_train import folder
from ripsat_policy import GraphBank
from scaling_bake import prepare as bake
from selective_trials import inputs


@torch.no_grad()
def trial(a, d, model, block, interface=None):
    ir = d / "program.json"
    prog = read(ir)
    layout = read(d / "layouts.json")[0]
    obs = a.out / "higher" / "observer"
    m = conditioned(a, d, obs)
    enc, scorer = load_enc(prog, a.actor)
    t = perf_counter()
    code = GraphBank([layout], enc.cat, enc.nodes).encode(scorer)
    enc_ms = (perf_counter() - t) * 1000
    assert code.shape[0] == 1 and len(layout[0][2]) == 2
    rmap = {rid: j for j, (rid, _, _) in enumerate(layout)}
    opened = []
    issued = set()
    paid = 0
    native_s = 0
    build_ms = address_ms = 0
    start = perf_counter()
    with subprocess.Popen(
        [
            a.runtime_binary,
            "online-ccp-v0.1",
            ir,
            "-",
            "audit",
            "--ept",
            "--address-seed",
            "39113",
        ],
        stdin=-1,
        stdout=-1,
        env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(obs)),
    ) as proc:
        client = Client(proc, 64, hashlib.sha256(ir.read_bytes()).hexdigest())
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                if f.get("final_publication"):
                    continue
                m.update(f)
                if interface is not None and layout[0][0] not in issued:
                    interface.publish(m, prog, f)
                client.run = f["run"]
                client.epoch = f["epoch"]
                for rid, _ in f["rules"]:
                    if rid not in rmap or rid in issued:
                        continue
                    j = rmap[rid]
                    issued.add(rid)
                    if j == 0:
                        if interface is not None:
                            cells, idx_bytes, build_ms, address_ms = interface.bind(
                                rid, code[0]
                            )
                        else:
                            z = public_view(m, prog, key=(rid, False))
                            assert [len(b) for b in z["addrs"]] == [8, 8]
                            assert z["wires"][1, 0].sum() == 1
                            data = inputs(z, False)
                            u = noise(np.random.default_rng(419), 32, 2)
                            torch.mps.synchronize()
                            t = perf_counter()
                            st = index(model, data)
                            torch.mps.synchronize()
                            build_ms = (perf_counter() - t) * 1000
                            idx_bytes = sum(
                                x.nbytes
                                for x in (
                                    *st[1][0].index.dictionaries,
                                    st[1][0].index.keys,
                                    st[1][0].index.owners,
                                    st[1][0].index.ends,
                                )
                            )
                            t = perf_counter()
                            sel = draw(data, st, u)[0].cpu().tolist()
                            address_ms = (perf_counter() - t) * 1000
                            cells = [
                                Cell(
                                    rid,
                                    tuple(z["addrs"][i][p] for i, p in enumerate(row)),
                                )
                                for row in sel
                            ]
                        batch = [{} for _ in cells]
                    else:
                        batch = []
                        cells = []
                        for job in opened:
                            refs = []
                            for pred, pc in layout[j][2]:
                                if pred not in job or (job[pred], pc) not in m.pub.live:
                                    break
                                k = job[pred], pc
                                refs.append((*k, m.pub.live[k][0]["version"]))
                            else:
                                batch.append(job)
                                cells.append(Cell(rid, tuple(refs)))
                    t = perf_counter()
                    replies = submit(client, cells, 64)
                    native_s += perf_counter() - t
                    paid += len(cells)
                    for job, (uid, status, *_) in zip(batch, replies, strict=True):
                        if status == 0:
                            job[j] = uid
                            if j == 0:
                                opened.append(job)
                client.seal()
            assert proc.wait() == 0 and "role" in f
        finally:
            client.close()
            m.close_observer()
    ops = sum(f["ept"]["signed_external"]) + sum(f["ept"]["signed_internal"])
    full = f["state_sha"] == read(d / "capture.json")["state_sha"]
    complete = sum(len(layout) - 1 in job for job in opened)
    assert full == (complete == 8) and paid >= ops
    return {
        "steps": len(layout),
        "block": block,
        "external": 2,
        "constraints": 1,
        "domain": 8,
        "slots": 32,
        "index_bytes": idx_bytes,
        "code_ms": enc_ms,
        "index_ms": build_ms,
        "address_ms": address_ms,
        "submit_collect_s": native_s,
        "native_verify_s": f["verify_seconds"],
        "native_rhs_s": f["rhs_phase_seconds"],
        "native_repair_s": f["repair_phase_seconds"],
        "wall_s": perf_counter() - start,
        "paid": paid,
        "ops": ops,
        "opened": len(opened),
        "completed": complete,
        "reference_match": full,
    }


def main(a):
    root = a.out / "higher"
    root.mkdir(exist_ok=True)
    model = frozen(a, a.seeds[0])
    # Reuse the native binaries but keep generated programs under the experiment output.
    data = root / "data"
    data.mkdir(exist_ok=True)
    scale = data / "unified-scale"
    if not scale.exists():
        scale.symlink_to(a.data / "unified-scale", target_is_directory=True)
    rows = []
    for n in (6, 32, 128, 256):
        bake(data, a.compiler, root, "fork", n, 2, 17, 8)
        d = folder(data, f"scale-fork-{n}-2-17-jobs8")
        for block in range(3):
            rows.append(trial(a, d, model, block))
        records(a.out / "higher.csv", rows)
        print(rows[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    main(args())
