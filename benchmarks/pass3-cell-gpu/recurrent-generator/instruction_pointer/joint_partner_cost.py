"""Synchronized component costs and a real publication delta, separate from live clocks."""

import json
from statistics import median
from time import perf_counter
import numpy as np
import torch
from binding_model import tensor, bit_lanes, read_packet
from binding_packets import packet
from binding_worlds import build
from first_parent import records
from joint_partner import model, batch, edge_view
from joint_partner_worlds import world, folder, options, ARMS


def timed(op):
    op()
    torch.mps.synchronize()
    times = []
    for _ in range(5):
        t = perf_counter()
        for _ in range(4):
            op()
        torch.mps.synchronize()
        times.append((perf_counter() - t) * 250)
    return median(times)


def growing(a, n, delta):
    job = ("publish", 600001 + delta, n, "two", 0, True)
    _, i, _, kind, f, held = job
    text = world(i, n, kind, f, held, (4, n))
    # Move actual physical facts into a different relation. Native Run 1 publishes
    # delta new Mid rows through a normal verified rule, before the measured Run 2.
    counter = 0
    lines = ["(relation Seed (i64 i64 i64))"]
    for line in text.splitlines():
        if line.startswith("(Mid "):
            if counter < delta:
                line = line.replace("(Mid ", "(Seed ", 1)
            counter += 1
        if line.startswith("(run-schedule"):
            lines.append("(rule ((Seed a b c)) ((Mid a b c)) :ruleset warm)")
        lines.append(line)
    assert counter == n
    build(a, (*job[:5], False, False), override="\n".join(lines) + "\n")
    d = folder(a, job)
    packet(a, d)
    z = read_packet(d / "binding.pkl")
    frames = [json.loads(s) for s in (d / "public.jsonl").read_text().splitlines()]
    f = next(f for f in frames if f["run"] == 2)
    changed = {(p["token"], p["op"], v["version"]) for p, v in f["updates"]}
    idx = [j for j, ref in enumerate(z["addrs"][1]) if ref in changed]
    assert len(idx) == delta and len(z["addrs"][1]) == n
    return z, idx


@torch.no_grad()
def measure(a):
    nets = {k: model(a, 9633, k) for k in ARMS}
    rows = []
    for n in (4, 32, 64, 256, 512, 1024):
        for kind, code in (("two", 1), ("chain", 3)):
            z = read_packet(
                folder(a, ("held", 300000 + code, n, kind, 0, True)) / "binding.pkl"
            )
            inp, layout = batch([z])
            noise = tensor(
                np.random.default_rng(802)
                .random((1, 32, len(z["banks"])))
                .astype(np.float32)
            )
            for arm, net in nets.items():
                if arm == "dense" and n > 32:
                    continue
                fut, edge = net.messages(inp, layout)
                e = edge_view(inp, 0)

                def infer():
                    return net((inp, layout), noise=noise)

                row = dict(
                    n=n,
                    kind=kind,
                    arm=arm,
                    pack_upload_ms=timed(lambda: batch([z])),
                    all_messages_ms=timed(lambda: net.messages(inp, layout)),
                    decode32_ms=timed(lambda: net.decode(inp, fut, edge, None, noise)),
                    forward32_ms=timed(infer),
                    partner_build_ms="",
                    root_readout_ms="",
                    summary_bytes="",
                    partner_feature_bytes="",
                    dense_pairs_per_page=(len(layout) * n * n if arm == "dense" else 0),
                    selected_edge_scores=(
                        0 if arm == "dense" else len(layout) * 32 * n
                    ),
                )
                if arm != "dense":
                    L, R = net.features(e, layout[0])
                    summary = R.sum(1)
                    row.update(
                        partner_build_ms=timed(
                            lambda: net.encode_side(e[3][1][1], layout[0][:, :, 1]).sum(
                                1
                            )
                        ),
                        root_readout_ms=timed(
                            lambda: net.reduce_score(net.evidence(L, summary), e)
                        ),
                        summary_bytes=summary.numel() * 4,
                        partner_feature_bytes=R.numel() * 4,
                    )
                rows.append(row)
    records(a.out / "components.csv", rows)
    updates = []
    for n in (64, 256, 1024):
        for delta in (1, 8, 32):
            z, idx = growing(a, n, delta)
            inp, layouts = batch([z])
            cols = layouts[0][:, :, 1]
            fields = inp[3][1][1]
            ids = tensor(np.array(idx))
            old = tensor(np.delete(np.arange(n), idx))
            for arm, net in nets.items():
                if arm == "dense":
                    continue

                def sum_features(f):
                    return net.encode_side(f, cols).sum(1)

                oldsum = sum_features(fields[:, old])
                small = fields[:, ids]
                actual = oldsum + sum_features(small)
                expected = sum_features(fields)
                torch.testing.assert_close(actual, expected, rtol=1e-5, atol=2e-4)

                def from_host():
                    extra = tensor(bit_lanes(z["banks"][1]["hash"][idx][None]))
                    return oldsum + sum_features(extra)

                torch.testing.assert_close(from_host(), expected, rtol=1e-5, atol=2e-4)
                updates.append(
                    dict(
                        n=n,
                        delta=delta,
                        arm=arm,
                        max_error=float((actual - expected).abs().max()),
                        device_insert_ms=timed(lambda: oldsum + sum_features(small)),
                        host_insert_ms=timed(from_host),
                        full_device_rebuild_ms=timed(lambda: sum_features(fields)),
                    )
                )
    records(a.out / "updates.csv", updates)


if __name__ == "__main__":
    torch.set_num_threads(1)
    measure(options().parse_args())
