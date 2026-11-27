"""Offline only. Preserve observed, unnormalized Query-Key evidence over every owner."""

import math

import torch

from cell_kv_runtime import native
from compatibility_study import SEEDS, align, checkpoint, policy
from compatibility_world import world
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding_study import save


@torch.no_grad()
def run(a):
    actor = load_actor(a.actor, True)
    models = {}
    for seed in SEEDS:
        net = policy(a, "D").eval()
        net.load_state_dict(torch.load(checkpoint(a, "D", seed), weights_only=True))
        models[seed] = net
    rows = []
    for i in range(32):
        novel = i >= 16
        name = f"{'extra-new' if novel else 'extra-seen'}-{i}"
        spec = (4 if novel else 1, "LR", 1, False, 900 if novel else 100, 841510 + i)
        ws = [world(a, actor, name, spec, f) for f in (False, True)]
        ex = [native(a, w, teacher="higher")[0] for w in ws]
        _, tids = align(*ex, ws[0])
        for seed, net in models.items():
            for f, (w, (state, _)) in enumerate(zip(ws, ex, strict=True)):
                net.prepare(w)
                m = net.state(w, state)
                q = net.actor.query(m["ctx"] + net.cache[1][m["menu"]])
                scores = q @ m["keys"].T / math.sqrt(q.size(1))
                support = scores.logsumexp(1) - math.log(scores.size(1))
                ix = [m["menu"].index(t) for t in tids]
                for mode, logits in (
                    ("current", m["lp"]),
                    ("qk_mass", support),
                    ("current_plus_mass", m["lp"] + support),
                ):
                    pair = logits[ix]
                    rows.append(
                        {
                            "case": name,
                            "seed": seed,
                            "flip": f,
                            "readout": mode,
                            "p_pair": float(pair.softmax(0)[f]),
                            "margin": float(pair[0] - pair[1]),
                        }
                    )
    save(a.out / "score-probe.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
