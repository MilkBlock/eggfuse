"""Bounded primitive-only transfer pilot with a shared frozen template sampler."""

from collections import Counter
import hashlib
import json
import os
import subprocess
from time import perf_counter
import numpy as np
import torch
from address_scores import mlp
from binding_model import Decoder, collate, parser, tensor
from binding_packets import public_view
from ccp_v01 import Client, read_repairs
from cell_transaction import memory_frame
from completion_context import read, write
from credit_scale_buffer import submit
from discrete_draft import Cell
from query_environment import conditioned
from recursive_coverage import snapshot, Target
from recursive_train import folder


def choose_templates(net, m, noise):
    ids = [r for r, h in m.ids if not h]
    if len(ids) == 1:
        return [ids[0]] * len(noise)
    # Read two representative rule vectors per active split and slot.
    # The static vocabulary is the original scheduled Primitive set.
    keys = tensor(torch.stack([m.graph((r, False)) for r in ids]).numpy())
    q = tensor(m.context().numpy()).expand(len(noise), -1)
    lo = torch.zeros(len(noise), dtype=torch.long, device="mps")
    hi = lo + len(ids)
    for level in range((len(ids) - 1).bit_length()):
        mid = (lo + hi) // 2
        left = (lo + mid - 1) // 2
        right = (mid + hi - 1) // 2
        prob = mlp(net.gate, q, keys[left.clamp_min(0)], keys[right], 0).sigmoid()
        take = tensor(noise[:, level]) < prob
        active = hi - lo > 1
        lo, hi = (
            torch.where(active & take, mid, lo),
            torch.where(active & ~take, mid, hi),
        )
    return [ids[i] for i in lo.cpu().tolist()]


def unpack(pipe, f):
    rows, hashes, retired, accepted = memory_frame(pipe, f)
    read_repairs(pipe, f)
    values = []
    offset = 0
    for uid, op, tab, v, fw, end in rows.tolist():
        values.append(
            [
                dict(token=uid, op=op),
                dict(
                    table=tab,
                    version=v,
                    forwarded=bool(fw),
                    hashes=hashes[offset:end].tolist(),
                ),
            ]
        )
        offset = end
    f.update(
        updates=values,
        accepted=accepted.tolist(),
        retired=[dict(token=int(t), op=int(o)) for t, o in retired],
    )


@torch.no_grad()
def execute(
    a,
    d,
    dest,
    net,
    arm,
    seed,
    block,
    draw,
    reference,
    *,
    parent_policy=None,
    address_seed=None,
    template_policy=None,
    audit_slots=False,
    paid_limit=None,
):
    dest.mkdir(exist_ok=True, parents=True)
    observer = dest / "observer.jsonl"
    export = dest / "graph.json"
    t = perf_counter()
    m = conditioned(a, d, observer)
    ir = d / "program.json"
    digest = hashlib.sha256(ir.read_bytes()).hexdigest()
    program = read(ir)
    events = []
    stats = Counter()
    count_by_rule = Counter()
    with subprocess.Popen(
        [
            a.runtime_binary,
            "online-ccp-v0.1",
            ir,
            "-",
            "audit",
            "--export",
            export,
            "--ept-origins" if audit_slots else "--ept",
            *(
                ["--address-seed", str(address_seed)]
                if address_seed is not None
                else []
            ),
        ],
        stdin=-1,
        stdout=-1,
        env=dict(
            os.environ,
            EGGFUSE_QUERY_OBSERVER=str(observer),
            **(
                {"EGGFUSE_ADMISSION_OBSERVER": str(dest / "admit.csv")}
                if audit_slots
                else {}
            ),
        ),
    ) as proc:
        client = Client(proc, 32, digest)
        try:
            for line in iter(proc.stdout.readline, b""):
                f = json.loads(line)
                if "role" in f:
                    break
                unpack(proc.stdout, f)
                if f.get("final_publication"):
                    continue
                m.update(f)
                r = client.run = f["run"]
                m.current_probe_run = r
                client.epoch = f["epoch"]
                rng = np.random.default_rng(draw + 47311 * r)
                if m.ids and (paid_limit is None or stats["paid"] < paid_limit):
                    # Common random numbers independent of success in a previous run.
                    noise = rng.random(
                        (a.slots, max(1, (len(m.ids) - 1).bit_length()))
                    ).astype(np.float32)
                    templates = (
                        choose_templates(net, m, noise)
                        if template_policy is None
                        else template_policy(net, m, program, noise)
                    )
                    stats["attempts"] += len(templates)
                    cells = [None] * len(templates)
                    for rid in dict.fromkeys(templates):
                        idx = [i for i, rule in enumerate(templates) if rule == rid]
                        if not m.roles[rid]:
                            for i in idx:
                                cells[i] = Cell(rid, ())
                            continue
                        z = public_view(m, program, key=(rid, False))
                        if any(not b for b in z["addrs"]):
                            stats["empty_domain"] += len(idx)
                            continue
                        k = len(z["banks"])
                        noise = tensor(rng.random((1, len(idx), k)).astype(np.float32))
                        if parent_policy is None:
                            _, chosen = net(collate([z]), draws=len(idx), noise=noise)
                            stats["parent_candidate_scores"] += len(idx) * sum(
                                len(b) for b in z["addrs"]
                            )
                        else:
                            chosen = parent_policy(z, noise, rng, stats)
                        for i, ix in zip(idx, chosen[0].cpu().tolist(), strict=True):
                            cells[i] = Cell(
                                rid, tuple(z["addrs"][j][p] for j, p in enumerate(ix))
                            )
                    signed = [c for c in cells if c is not None]
                    if paid_limit is not None:
                        signed = signed[: paid_limit - stats["paid"]]
                    count_by_rule.update(c.rule for c in signed)
                    replies = iter(submit(client, signed, 32))
                    if audit_slots:
                        from cell_transaction import STATUS

                        for slot, (rid, cell) in enumerate(
                            zip(templates, cells, strict=True)
                        ):
                            reply = next(replies, None) if cell is not None else None
                            unsent = (
                                "empty_domain" if cell is None else "budget_unsubmitted"
                            )
                            events.append(
                                dict(
                                    run=r,
                                    epoch=client.epoch,
                                    slot=slot,
                                    rule=rid,
                                    dirty=bool(m.rule_features[m.rule_index[rid], 0]),
                                    watermark=dict(f["rules"])[rid],
                                    epoch_at_submit=client.epoch if reply else None,
                                    refs=cell.refs if cell is not None else None,
                                    status=STATUS[reply[1]] if reply else unsent,
                                    uid=reply[0] if reply else None,
                                )
                            )
                        assert next(replies, None) is None
                    stats["paid"] += len(signed)
                client.seal()
            if proc.wait() != 0 or "role" not in f:
                raise RuntimeError("incomplete native execution")
        finally:
            client.close()
            m.close_observer()
    wall = perf_counter() - t
    if audit_slots:
        origins = dict(f["ept"]["origins"])
        for event in events:
            event["gain"] = origins.get(event["uid"], 0)
        write(dest / "slots.json", events)
        write(
            dest / "accepted.json",
            dict(
                schema="cell-token-replay/permuted-v1",
                address_seed=address_seed,
                program_sha256=digest,
                requests=list(client.offline_tape(client.run)),
                repair_events=[],
            ),
        )
    target, initial = reference
    facts = sorted(target.match(read(export)) - initial)
    ops = sum(f["ept"]["signed_external"]) + sum(f["ept"]["signed_internal"])
    result = dict(
        arm=arm,
        seed=seed,
        draw=draw,
        block=block,
        covered=len(facts),
        reference=len(target.gold) - len(initial),
        facts=facts,
        ops=ops,
        ept=ops / max(1, stats["paid"]),
        eps=ops / wall,
        wall=wall,
        stats=stats,
        receipts=f["counts"],
        graph=f["state_sha"],
    )
    write(dest / "result.json", result)


if __name__ == "__main__":
    p = parser()
    p.add_argument("--slots", type=int, default=8)
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        root = a.out / "egg-online" / case
        root.mkdir(exist_ok=True, parents=True)
        d = folder(a.data, case)
        t = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, root / "reference.json")[0],
        )
        initial = t.match(
            snapshot(a.data, d, "reference", "-", 0, root / "initial.json")[0]
        )
        for seed in a.seeds:
            for block in range(2):
                for arm in a.arms if block == 0 else a.arms[::-1]:
                    dest = root / f"{seed}-{arm}-{block}"
                    if (dest / "result.json").exists():
                        continue
                    net = Decoder(a, arm).to("mps").eval()
                    net.load_state_dict(
                        torch.load(
                            a.out / "weights" / str(seed) / f"{arm}.pt",
                            weights_only=True,
                        )
                    )
                    execute(a, d, dest, net, arm, seed, block, seed + 101, (t, initial))
                    print(case, seed, block, arm, flush=True)
