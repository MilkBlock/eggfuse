"""Differential audit on native states. Freeze flags and hypothetical sensitivities are separate."""

from contextlib import ExitStack
from unittest.mock import patch

import torch

from cell_kv_model import CellKV
from cell_kv_runtime import native
from partner_index_worlds import args
from token_embedding_study import save
from value_read_eval import models
from value_read_model import lane_products
from value_read_train import SINGLE, STEPS, output
from value_read_world import CUBES, SCHEMAS, field_pair, instance


def gradient(net, w, s, token):
    net.prepare(w)
    # Input sensitivities for frozen weights are an offline counterfactual.
    net.actor.input_content.requires_grad_(True)
    net.actor.latent.requires_grad_(True)
    queries = []

    def record(_, inputs, result):
        queries.append(result)

    try:
        with ExitStack() as stack:
            stack.callback(net.actor.query.register_forward_hook(record).remove)
            m = net.state(w, s)
            loss = net.token_loss(w, m, token)
            items = {
                "global_q": queries[0],
                "candidate_q": queries[1],
                "final_projection_output": queries[2],
                "address_q": queries[3],
                "owner_key": m["keys"],
                "owner_value": m["vals"],
                "port_key": m["ek"],
                "Wq": net.actor.query.weight,
                "Wk": net.actor.input_content.weight,
                "Wv": net.actor.latent.weight,
                "Wrole": net.actor.input_role.weight,
                "GRU_ih": net.actor.next_read.weight_ih,
                "GRU_hh": net.actor.next_read.weight_hh,
            }
            groups = {}
            for label, obj in (
                ("complete_ce", loss),
                ("template_ce", -m["lp"][m["menu"].index(token[0])]),
            ):
                grads = torch.autograd.grad(
                    obj, list(items.values()), allow_unused=True, retain_graph=True
                )
                groups[label] = {
                    k: float(g.norm()) if g is not None else None
                    for k, g in zip(items, grads, strict=True)
                }
            # Isolate the owner-address softmax partial w.r.t. candidate Query; the
            # interface reader and the final score can still use q on other paths.
            logits = queries[1] @ m["keys"].detach().T / 32**0.5
            weight = logits.softmax(-1)
            jac = torch.autograd.grad(weight[0, 0], queries[1])[0]
            groups["owner_weight_q_sensitivity"] = float(jac.norm())
            return {
                "nowners": len(m["keys"]),
                "nports": len(m["refs"]),
                "menu": m["menu"],
                "token": token,
                "complete_ce": float(loss.detach()),
                "gradients": groups,
            }
    finally:
        net.actor.input_content.requires_grad_(False)
        net.actor.latent.requires_grad_(False)


def run(a):
    nets = models(a)
    actor = next(iter(nets.values())).actor
    grad = []
    # Includes the genuinely singleton root plus multiple-owner and multiport states.
    for distract in (False, True):
        w = instance(a, actor, SCHEMAS[0], 97005, (1, 0, 0), 1, distract)
        trail = native(a, w, teacher="higher")
        for stage, (s, ts) in (("entry", trail[0]), ("downstream", trail[-1])):
            token = next((item for item in ts if item[0] >= w.primitives), ts[0])
            for (v, seed, step), net in nets.items():
                if seed == 71 and step in (0, STEPS):
                    grad.append(
                        dict(
                            v=v,
                            init_or_updates=step,
                            distract=distract,
                            stage=stage,
                            **gradient(net, w, s, token),
                        )
                    )
    save(output(a) / "gradients.json", grad)
    controls = []
    with torch.no_grad():
        # New cubes; perturb only the payload supplied to the template reader.
        for schema in (SCHEMAS[0], SCHEMAS[3], SCHEMAS[4], SCHEMAS[-1]):
            for pool in (97111, 97112):
                for bits in CUBES:
                    w = instance(a, actor, schema, pool, bits)
                    s, ts = native(a, w, teacher="higher")[0]
                    (tid,) = [t for t, refs in ts if t >= w.primitives]
                    for (v, seed, step), net in nets.items():
                        if v != "C" or step not in (SINGLE, STEPS):
                            continue
                        net.prepare(w)
                        for control in (
                            "intact",
                            "no_fields",
                            "pooled_roles",
                            "uniform_lanes",
                            "same_field_query",
                            "swap_roles",
                            "no_gru",
                        ):
                            with ExitStack() as stack:
                                if control not in ("intact", "no_gru"):

                                    def substitute(
                                        q, ports, mode=control, layout=schema
                                    ):
                                        if mode == "no_fields":
                                            return None
                                        words = [list(p[4]) for p in ports]
                                        if mode == "swap_roles":
                                            j, k = field_pair(layout[0])
                                            other = 3 - j - k
                                            for row in words:
                                                row[k], row[other] = row[other], row[k]
                                        lanes, role = lane_products(words)
                                        if mode == "pooled_roles":
                                            role = role.mean(0).expand_as(role)
                                        if mode == "same_field_query":
                                            q = q.mean(0).expand_as(q)
                                        if mode == "uniform_lanes":
                                            q = torch.zeros_like(q)
                                        return torch.einsum(
                                            "td,pfd,fh->tph", q.softmax(-1), lanes, role
                                        )

                                    stack.enter_context(
                                        patch.object(net, "read_interface", substitute)
                                    )
                                if control == "no_gru":
                                    stack.enter_context(
                                        patch.object(
                                            net,
                                            "template_readout",
                                            CellKV.template_readout.__get__(net),
                                        )
                                    )
                                m = net.state(w, s)
                                lp = m["lp"][
                                    [
                                        m["menu"].index(t)
                                        for t in (w.primitives, w.primitives + 1)
                                    ]
                                ]
                                gold = tid - w.primitives
                                controls.append(
                                    {
                                        "control": control,
                                        "step": step,
                                        "schema": list(schema),
                                        "pool": pool,
                                        "bits": list(bits),
                                        "seed": seed,
                                        "gold": gold,
                                        "gold_margin": float(lp[gold] - lp[1 - gold]),
                                        "refs": [s["ports"][0][0]],
                                        "p_pair": float(lp.softmax(0)[gold]),
                                    }
                                )
                        net.static_cache.clear()
    save(output(a) / "controls.json", controls)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
