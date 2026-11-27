"""Paired input interventions on an actually published two-input native instance."""

import torch

from cell_kv_model import CellKV
from cell_kv_runtime import native
from partner_index_worlds import args
from token_embedding import TokenEmbedding
from token_embedding_study import VARIANTS, held, initial, save


@torch.no_grad()
def run(a):
    states = []
    net = CellKV(a, "C", True).eval()
    net.load_state_dict(initial())

    class Recorder:
        def prepare(self, w):
            net.prepare(w)

        def generate(self, w, s, rng, slots):
            states.append(s)
            return net.generate(w, s, rng, slots)

    for w in held(a):
        states.clear()
        for draw in (193, 827, 541, 911):
            result = native(a, w, policy=Recorder(), seed=draw)
            ref = None
            for s in states:
                live = {p[0] for p in s["ports"]}
                ref = next(
                    (
                        p
                        for p in s["ports"]
                        if p[2] in w.finals
                        and len(p[6]) == 2
                        and p[6][0] != p[6][1]
                        and all(r in live for r in p[6])
                    ),
                    None,
                )
                if ref is not None:
                    break
            if ref is not None:
                break
            states.clear()
        if ref is not None:
            break
    if ref is None:
        raise ValueError("no published two-parent instance observed")
    rows = []
    for v in VARIANTS:
        model = TokenEmbedding(a, v, initial()).eval()
        model.prepare(w)
        orig = model.state(w, s)
        if v == "current":
            baseline = net.state(w, s)
            for k in ("keys", "vals", "lp", "ek", "ctx"):
                torch.testing.assert_close(orig[k], baseline[k], rtol=0, atol=0)
        for edit in (
            "swap_parent_roles",
            "remove_parent",
            "toggle_forwarded",
            "change_output_bits",
            "rename_op",
        ):
            ports = []
            for p in s["ports"]:
                r, owner, tid, table, fields, fw, parents = p
                if owner == ref[1]:
                    if edit == "remove_parent":
                        parents = parents[1:]
                    elif edit == "swap_parent_roles":
                        parents = tuple(reversed(parents))
                    elif edit == "toggle_forwarded":
                        fw = not fw
                    elif edit == "change_output_bits":
                        fields = (fields[0] ^ 127, *fields[1:])
                    elif edit == "rename_op":
                        r = (r[0], r[1] + 100, r[2])
                ports.append((r, owner, tid, table, fields, fw, parents))
            mem = model.state(w, dict(s, ports=ports))
            g = int(orig["group"][orig["pos"][ref[0]]])

            def diff(name, idx, mem=mem, orig=orig):
                return float((mem[name][idx] - orig[name][idx]).norm())

            rows.append(
                {
                    "v": v,
                    "edit": edit,
                    "key": diff("keys", g),
                    "value": diff("vals", g),
                    "port": diff("ek", orig["pos"][ref[0]]),
                }
            )
    save(
        a.out / "interventions.json",
        {
            "case": w.dir.name,
            "draw": draw,
            "run": s["run"],
            "port": ref,
            "graph": result["graph"],
            "rows": rows,
        },
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
