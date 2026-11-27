"""Materialize the frozen GNN/Actor view and ordered fields of every published row."""

import json
import os
import pickle
import numpy as np
import torch

from completion_context import frames, native, read, write
from discovery_states import cli

F = 4


def public_view(m, program, exact=None, *, key=None, limit=None, visible=None):
    if key is None:
        (key,) = m.ids
    rule, higher = key
    assert not higher
    recipe = program["recipe"]["rules"][rule]
    roles = recipe["interface"]["rows"][:limit]
    slots = [[c.get("slot") for c in r["columns"]] for r in roles]
    width = max(F, max(map(len, slots), default=0))
    wires = np.zeros((len(slots), len(slots), width, width), np.float32)
    for j, row in enumerate(slots):
        for prev in range(j):
            for c, s in enumerate(slots[prev]):
                for col, t in enumerate(row):
                    wires[j, prev, c, col] = float(s is not None and s == t)
    banks = []
    addrs = []
    for tab, row in zip(m.roles[rule][:limit], slots, strict=True):
        addresses = []
        hashes = []
        raw = []
        rows = []
        for addr in m.rows[tab]:
            if addr not in m.pub.live or (visible is not None and addr not in visible):
                continue
            v = m.pub.live[addr][0]
            addresses.append((*addr, v["version"]))
            h = v["hashes"]
            fields = exact[addresses[-1]] if exact is not None else []
            assert len(h) == len(row) <= width and (
                exact is None or len(fields) == len(h)
            )
            hashes.append(list(h) + [0] * (width - len(h)))
            bits = []
            for field in fields:
                if set(field) not in ({"Int"}, {"Eq"}):
                    raise ValueError(f"unsupported exact diagnostic field {field!r}")
                bits.append(next(iter(field.values())) % (1 << 64))
            raw.append(bits + [0] * (width - len(bits)))
            rows.append(m.key(addr).numpy())
        banks.append(
            dict(
                row=np.array(rows),
                hash=np.array(hashes, np.uint64),
                raw=np.array(raw, np.uint64),
                last=next((j for j, x in enumerate(addresses) if x[:2] == m.last), -1),
            )
        )
        addrs.append(addresses)
    return dict(
        rule=rule,
        banks=banks,
        addrs=addrs,
        slots=slots,
        wires=wires,
        h=(m.context() + m.graph(key)).tanh().numpy(),
        roles=m.enc.nodes[m.enc.cat.inputs["generated", rule][:limit]].numpy(),
        owners=len(m.pub.live),
    )


@torch.no_grad()
def packet(a, d):
    info = read(d / "ok.json")
    dest = d / "binding.pkl"
    if dest.exists():
        return
    native(
        a,
        d,
        "replay",
        d / "prefix.json",
        2,
        "--memory",
        d / "public.jsonl",
        env=dict(
            os.environ,
            EGGFUSE_QUERY_OBSERVER=str(d / "query.jsonl"),
            EGGFUSE_REPLAY_FIELD_VALUES="1",
        ),
    )
    m = frames(a, d)  # observer produced by the verified tape, validated again below
    m.observer_path = d / "query.jsonl"
    exact = {}
    try:
        for line in (d / "public.jsonl").read_text().splitlines():
            frame = json.loads(line)
            for addr, ver, vals in frame["observed_fields"]:
                exact[addr["token"], addr["op"], ver] = vals
            m.update(frame)
            if frame["run"] == 2:
                break
        obj = public_view(m, read(d / "program.json"), exact)
        addrs = obj["addrs"]
        gold = [
            [
                addrs[j].index(
                    (p["address"]["token"], p["address"]["op"], p["version"])
                )
                for j, p in enumerate(q["parents"])
            ]
            for q in info["gold"]
        ]
        assert all(not m.owner_contract(obj["rule"], a) for a in addrs[0])
        obj.update(
            path=d.name,
            split=info["split"],
            size=info["size"],
            layout=info["layout"],
            instance=info["instance"],
            order=info["order"],
            gold=gold,
            warm=info["warm"],
        )
        if info["layout"] == "merge":
            verify_aliases(a, d, obj, info)
        with dest.open("wb") as f:
            pickle.dump(obj, f, protocol=5)
    finally:
        m.close_observer()


def verify_aliases(a, d, z, info):
    # Offline intervention: execute each replacement alone from the same prefix.
    # Match the complete native graph and effective contribution to the canonical proof.
    tape = read(d / "prefix.json")
    signed = []
    owners = []
    for group, (target, q) in enumerate(zip(z["gold"], info["gold"], strict=True)):

        def trial(j):
            t, o, v = z["addrs"][-1][j]
            repl = dict(
                q,
                parents=[
                    *q["parents"][:-1],
                    dict(address=dict(token=t, op=o), version=v),
                ],
            )
            file = d / "alias-probe.json"
            write(file, dict(tape, requests=[*tape["requests"], repl]))
            rep = native(a, d, "replay", file, 2, "--ept-origins")
            return (rep["state_sha"], dict(rep["ept"]["origins"]).get(q["token"], 0))

        reference = trial(target[-1])
        assert reference[1] == 1
        for j in range(len(z["addrs"][-1])):
            if trial(j) == reference:
                signed.append([*target[:-1], j])
                owners.append(group)
    (d / "alias-probe.json").unlink()
    z["gold"] = signed
    z["groups"] = owners


if __name__ == "__main__":
    p = cli()
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    a = p.parse_args()
    torch.set_num_threads(1)
    for j, path in enumerate(
        sorted((a.out / "worlds").glob("*/*/ok.json"))[a.shard :: a.shards]
    ):
        packet(a, path.parent)
        if j % 250 == 0:
            print(j, flush=True)
