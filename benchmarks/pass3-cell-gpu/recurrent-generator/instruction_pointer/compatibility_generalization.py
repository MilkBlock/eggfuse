"""Independent filler pairs, fit-set reproduction and a two-state CE capacity control."""

import torch

from cell_kv_runtime import native
from compatibility_eval import diagnose
from compatibility_study import ARMS, SEEDS, align, checkpoint, policy
from compatibility_world import cases, world
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding_study import save


def run(a):
    actor = load_actor(a.actor, True)
    models = {}
    for arm in ARMS:
        for seed in SEEDS[:1] if arm == "A" else SEEDS:
            net = policy(a, arm).eval()
            net.load_state_dict(torch.load(checkpoint(a, arm, seed), weights_only=True))
            models[arm, seed] = net
    corpus = torch.load(a.out / "training.pt", weights_only=False)
    name, sp = next(cases("fit"))
    ws = [world(a, actor, name, sp, f) for f in (False, True)]
    ex = [corpus[w.dir.name][0] for w in ws]
    ref, tids = align(*ex, ws[0])
    for seed in SEEDS:
        # Equal total CE exposures, explicitly a memorization diagnostic.
        torch.manual_seed(seed)
        net = policy(a, "D").train()
        opt = torch.optim.AdamW(
            (p for p in net.parameters() if p.requires_grad),
            lr=0.0015,
            weight_decay=0.0,
        )
        gen = torch.Generator().manual_seed(seed)
        for _ in range(720):
            terms = []
            for f, w in enumerate(ws):
                net.prepare(w)
                s, ts = ex[f]
                m = net.state(w, s)
                terms.append(net.token_loss(w, m, (tids[f], (ref,))))
                for _ in range(2):
                    rows = corpus[w.dir.name]
                    s, ts = rows[int(torch.randint(len(rows), (1,), generator=gen))]
                    token = ts[int(torch.randint(len(ts), (1,), generator=gen))]
                    terms.append(net.token_loss(w, net.state(w, s), token))
            opt.zero_grad(set_to_none=True)
            torch.stack(terms).mean().backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
            opt.step()
        torch.save(net.state_dict(), a.out / f"fit-one-{seed}.pt")
        models["fit-one", seed] = net.eval()
    rows = []
    with torch.no_grad():
        specs = list(cases("fit"))
        # 16 new filler pairs per layout family in addition to the main test.
        for i in range(32):
            new = i >= 16
            specs.append(
                (
                    f"{'extra-new' if new else 'extra-seen'}-{i}",
                    (4 if new else 1, "LR", 1, False, 900 if new else 100, 841510 + i),
                )
            )
        for name, sp in specs:
            ws = [world(a, actor, name, sp, f) for f in (False, True)]
            ex = [
                corpus[w.dir.name][0]
                if name.startswith("fit-")
                else native(a, w, teacher="higher")[0]
                for w in ws
            ]
            ref, tids = align(*ex, ws[0])
            for (arm, seed), net in models.items():
                for r in diagnose(net, ws, ex, ref, tids):
                    rows.append(dict(case=name, arm=arm, seed=seed, **r))
            save(a.out / "generalization.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
