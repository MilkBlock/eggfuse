"""Native paired trials and held-out interfaces for the four frozen readers."""

import copy
import json
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World, compile_world
from operand_read_model import OperandRead
from operand_read_train import dest
from partner_index_worlds import args
from value_read_eval import Observe
from value_read_model import ValueRead
from value_read_train import SEEDS, STEPS
from value_read_world import CUBES, SCHEMAS, field_pair, filler_values, key, program


def load(a, arm, seed, step=STEPS):
    net = ValueRead(a, "C") if arm == "A" else OperandRead(a, arm)
    if step == 0:
        return net.eval()
    path = (
        a.out / "rich" / f"C-{seed}-{step}.pt"
        if arm == "A"
        else dest(a) / f"{arm}-{seed}-{step}.pt"
    )
    net.load_state_dict(torch.load(path, weights_only=True))
    return net.eval()


def fixture(a, actor, label, schema, pool, bits):
    _w, _g, _o = schema
    if label == "known":
        return World(a.out / "worlds" / key(schema, pool, bits), actor)
    depth = 4 if label == "deep" else 1
    source = program(schema, pool, bits, depth)
    if label in ("width", "shift"):
        fields = (
            ("x", "y", "z", "u", "v") if label == "width" else ("u", "x", "v", "y", "z")
        )
        vals = filler_values(pool)
        values = dict(zip("xyzuv", [*(vals[i] for i in bits), *vals[2:4]], strict=True))
        source = source.replace("i64 i64 i64)", "i64 i64 i64 i64 i64)").replace(
            "x y z)", " ".join(fields) + ")"
        )
        source = (
            "\n".join(
                "(Seed " + " ".join(str(values[f]) for f in fields) + ")"
                if line.startswith("(Seed ")
                else line
                for line in source.splitlines()
            )
            + "\n"
        )
    return World(
        compile_world(a, f"operand-{label}-" + key(schema, pool, bits, depth), source),
        actor,
    )


def inspect(net, w, state, target, arm, positions):
    t, _refs = target
    queries = []
    with net.actor.query.register_forward_hook(
        lambda mod, inp, out: queries.append(out)
    ):
        net.audit = True
        net.prepare(w)
        m = net.state(w, state)
        j = m["menu"].index(t)
        loss = net.token_loss(w, m, target)
        q = queries[1] if arm == "A" else net.trace[1]
        grad = torch.autograd.grad(loss, q)[0]
        hs = m["lp"][
            [m["menu"].index(tid) for tid in range(w.primitives, len(w.layouts))]
        ]
        if arm == "A":
            weights = q[j].softmax(-1)
            mass = None
        else:
            weights = net.trace[0][0, j]
            f = len(state["ports"][0][4])
            i, k = positions
            if arm == "B":
                pairs = torch.triu_indices(f, f, offset=1)
                mass = weights[((pairs[0] == i) & (pairs[1] == k)).nonzero().item()]
            else:
                mass = weights[0, i] * weights[1, k] + weights[0, k] * weights[1, i]
            mass = float(mass.detach())
        net.audit = False
        margin = float((hs[0] - hs[1]).detach())
        return {
            "margin": margin,
            "p_full": float((-loss).detach().exp()),
            "grad": float(grad.norm()),
            "mass": mass,
            "p_branch": float(hs.softmax(0)[t - w.primitives].detach()),
            "weights": weights.detach().tolist(),
        }


def evaluate(
    a, labels=("known", "position", "width", "shift", "deep"), result_dir=None
):
    nets = {(arm, seed): load(a, arm, seed) for arm, seed in product("ABCD", SEEDS)}
    actor = next(iter(nets.values())).actor
    signatures = set()
    for s in SCHEMAS:
        signatures.update(
            digest(World(a.out / "worlds" / key(s, 71001, CUBES[0]), actor))
        )
    diag = []
    live = []
    result_dir = result_dir or dest(a)
    for label in labels:
        pools = range(81011, 81015) if label == "known" else range(108111, 108114)
        wirings = (2,) if label == "position" else (0, 1)
        for pool, g, o, bits in product(pools, range(2), range(2), CUBES):
            reference_state = None
            for wiring in wirings:
                with TemporaryDirectory() as tmp:
                    local = copy.copy(a)
                    if label != "known":
                        local.out = Path(tmp)
                    w = fixture(local, actor, label, (wiring, g, o), pool, bits)
                    sig = digest(w)
                    if label != "known":
                        assert signatures.isdisjoint(sig)
                    state, targets = native(a, w, teacher="higher")[0]
                    if reference_state is not None:
                        assert state == reference_state
                    reference_state = state
                    (target,) = [pair for pair in targets if pair[0] >= w.primitives]
                    positions = field_pair(wiring)
                    if label == "shift":
                        positions = tuple((1, 3, 4)[j] for j in positions)
                    meta = {
                        "label": label,
                        "wire": wiring,
                        "g": g,
                        "o": o,
                        "pool": pool,
                        "bits": list(bits),
                        "gold": target[0] - w.primitives,
                        "signatures": sig,
                    }
                    for (arm, seed), net in nets.items():
                        diag.append(
                            dict(
                                **meta,
                                arm=arm,
                                seed=seed,
                                **inspect(net, w, state, target, arm, positions),
                            )
                        )
                    # Live slice includes both guard polarities, both fillings on conflicting inputs,
                    # both wirings when available and both arithmetic assignments.
                    live_corners = (
                        ((0, 0, 0), (0, 0, 1))
                        if label == "position"
                        else ((0, 0, 1), (0, 1, 0))
                    )
                    if pool == pools[0] and bits in live_corners:
                        for draw, block in product((193, 827), (0, 1)):
                            order = list(nets)
                            if (block + g + o + wiring + (draw == 827)) % 2:
                                order.reverse()
                            for arm, seed in order:
                                net = nets[arm, seed]
                                net.static_cache.clear()
                                spy = Observe(net)
                                with torch.no_grad():
                                    result = native(a, w, policy=spy, seed=draw)
                                s, out = spy.entry
                                (ref,) = [
                                    p[0]
                                    for p in s["ports"]
                                    if p[3] == w.tabs.index("Seed")
                                ]
                                hit = sum(token == (target[0], (ref,)) for token in out)
                                live.append(
                                    dict(
                                        **meta,
                                        arm=arm,
                                        seed=seed,
                                        draw=draw,
                                        block=block,
                                        hits=hit,
                                        slots=len(out),
                                        **result,
                                    )
                                )
                    for net in nets.values():
                        net.static_cache.clear()
        print(label, len(diag), len(live), flush=True)
        for name, records in (("diagnostic", diag), ("native", live)):
            (result_dir / (name + ".json")).write_text(
                json.dumps(records, separators=(",", ":"))
            )


if __name__ == "__main__":
    torch.set_num_threads(1)
    evaluate(args())
