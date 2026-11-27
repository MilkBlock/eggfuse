"""Offline path-specific gradient and representation probes on native replay states."""

import torch

from cell_kv_model import CellKV, public_values
from cell_kv_runtime import native
from cell_kv_study import digest, groups
from partner_index_worlds import args
from ripsat_policy import GraphBank
from token_embedding import TokenEmbedding
from token_embedding_study import SEEDS, VARIANTS, held, initial, save, weights


def path_trace(a, w, s, target):
    net = CellKV(a, "C", True).train()
    net.load_state_dict(initial())
    net.prepare(w)
    nodes, codes, types = net.cache
    m = net.state(w, s)
    tid, refs = target
    i = m["pos"][refs[0]]
    p = m["ports"][i]
    g = int(m["group"][i])
    prod = p[2]
    assert prod not in m["menu"] and prod != tid and prod >= 0
    tensors = dict(
        nodes=nodes,
        codes=codes,
        table_types=types,
        **{k: m[k] for k in ("owners", "keys", "vals", "ctx", "ek", "ext", "lp")},
    )
    for tensor in tensors.values():
        tensor.retain_grad()
    loss = net.token_loss(w, m, target)
    loss.backward()

    def norm(t):
        return float(t.detach().norm())

    layers = dict(groups(net), age=[net.actor.age])
    bk = GraphBank(w.layouts[w.primitives :], w.cat, nodes)
    out = {
        "case": w.dir.name,
        "target": target,
        "run": s["run"],
        "epoch": s["epoch"],
        "physical": p[0],
        "owner": p[1],
        "producer_template": prod,
        "parents": p[6],
        "visible_parent_count": sum(r in m["pos"] for r in p[6]),
        "members": [s["ports"][j][:6] for j in m["siblings"][g].tolist()],
        "actor_class": type(net.actor).__name__,
        "name_mode": net.actor.name_mode,
        "shape": {k: list(v.shape) for k, v in tensors.items()},
        "recipe_edges": len(w.cat.edges),
        "layout_batch": [list(t.shape) for t in bk.batch(slice(None), "cpu")],
        "selected_key": m["keys"][g].tolist(),
        "selected_value": m["vals"][g].tolist(),
        "ce": loss.item(),
        "producer_code_grad": norm(codes.grad[prod]),
        "consumer_code_grad": norm(codes.grad[tid]),
        "selected_key_grad": norm(m["keys"].grad[g]),
        "selected_value_grad": norm(m["vals"].grad[g]),
        "group_grad": {
            k: sum(
                norm(p.grad) ** 2
                for layer in layers[k]
                for p in layer.parameters()
                if p.grad is not None
            )
            ** 0.5
            for k in layers
        },
        "parameters": {
            k: {
                "n": p.numel(),
                "shape": list(p.shape),
                "grad": None if p.grad is None else norm(p.grad),
            }
            for k, p in net.named_parameters()
        },
    }
    return out


def audit(a):
    traces = []
    results = []
    collisions = []
    layouts = []
    for w in held(a):
        layouts.append(
            {
                "case": w.dir.name,
                "signatures": digest(w),
                "sizes": [len(x) for x in w.layouts[-2:]],
                "interface": [
                    (w.roles[x[0][0]], w.outputs[x[0][0]], w.outputs[x[-1][0]])
                    for x in w.layouts[-2:]
                ],
            }
        )
        states = native(a, w, teacher="higher")
        pairs = [(s, t) for s, ts in states for t in ts if t[0] in w.finals]
        if not traces:
            traces.append(path_trace(a, w, *pairs[0]))
            rows = native(a, w, teacher="primitive")
            s, t = next((s, t) for s, ts in rows for t in ts if t[0] in w.finals)
            traces.append(path_trace(a, w, s, t))
        with torch.no_grad():
            for v in VARIANTS:
                for seed in SEEDS:
                    net = TokenEmbedding(a, v, initial()).eval()
                    net.load_state_dict(
                        torch.load(weights(a, v, seed), weights_only=True)
                    )
                    net.prepare(w)
                    for s, target in pairs:
                        m = net.state(w, s)
                        p = s["ports"][m["pos"][target[1][0]]]
                        owner, tid = p[1:3]
                        assert tid >= w.primitives
                        g = int(m["group"][m["pos"][target[1][0]]])
                        for ab in ("keep", "other_higher", "root"):
                            alt = {
                                "keep": tid,
                                "other_higher": 2 * w.primitives + 1 - tid,
                                "root": w.root,
                            }[ab]
                            # Only replace the learned owner structure. Keep true port
                            # contracts/labels and the entire candidate catalogue fixed.
                            old = net.instance_embedding

                            def replace(
                                world,
                                ports,
                                pos,
                                siblings,
                                group,
                                source,
                                value,
                                indices=m["siblings"][g],
                                code=net.cache[1][alt],
                                encode=old,
                            ):
                                src = source.clone()
                                src[indices] = code
                                return encode(
                                    world, ports, pos, siblings, group, src, value
                                )

                            net.instance_embedding = replace
                            try:
                                mod = net.state(w, s)
                            finally:
                                del net.instance_embedding
                            results.append(
                                {
                                    "case": w.dir.name,
                                    "v": v,
                                    "seed": seed,
                                    "tid": tid,
                                    "owner": owner,
                                    "probe": ab,
                                    "p": float((-net.token_loss(w, mod, target)).exp()),
                                    "key_shift": float(
                                        (m["keys"][g] - mod["keys"][g]).norm()
                                    ),
                                    "value_shift": float(
                                        (m["vals"][g] - mod["vals"][g]).norm()
                                    ),
                                }
                            )
                        for h in range(g):
                            p2 = s["ports"][int(m["siblings"][h][0])]
                            if p2[2] == tid:
                                collisions.append(
                                    {
                                        "case": w.dir.name,
                                        "v": v,
                                        "seed": seed,
                                        "owners": [owner, p2[1]],
                                        "key_distance": float(
                                            (m["keys"][g] - m["keys"][h]).norm()
                                        ),
                                    }
                                )
    for trace in traces:
        assert trace["producer_code_grad"] > 0
    # Bit 45 of the first scalar cannot affect the historical 32-lane summary.
    assert torch.equal(*public_values([(21,), (21 + (1 << 45),)]).unbind())
    save(a.out / "layouts.json", layouts)
    save(a.out / "trace.json", traces)
    save(a.out / "owner.json", results)
    save(a.out / "instances.json", collisions)


if __name__ == "__main__":
    torch.set_num_threads(1)
    audit(args())
