"""Fixed-budget transfer control. Replay and mixed restarts use the same optimizer and CE exposure."""

import copy
import json
import os
import random
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World
from interface_role_eval import diagnostic
from interface_role_model import RoleRead
from interface_role_train import dest
from interface_role_world import mixed
from partner_index_worlds import args
from token_embedding_study import fixed_digest
from value_read_train import SEEDS, SINGLE, STEPS
from value_read_world import CUBES, SCHEMAS, key


def corpus(a, net, mode):
    rows = []
    for i in range(32):
        with TemporaryDirectory() as tmp:
            local = copy.copy(a)
            local.out = Path(tmp)
            if mode == "mixed":
                w = mixed(local, net.actor, 135000 + i // 2, i % 2, depth=1)
            else:
                w = World(
                    a.out
                    / "worlds"
                    / key(SCHEMAS[i % 8], 71001 + i // 8, CUBES[(i % 8 + i // 8) % 8]),
                    net.actor,
                )
            traj = native(a, w, teacher="higher")
            rows.append((w, traj))
    return rows


def transfer(a, mode):
    curves = []
    for seed in SEEDS:
        net = RoleRead(a, "C")
        net.load_state_dict(
            torch.load(dest(a) / f"C-{seed}-{SINGLE}.pt", weights_only=True)
        )
        net.train()
        initial = fixed_digest(net)
        data = corpus(a, net, mode)
        rng = random.Random(seed)
        opt = torch.optim.AdamW(
            [p for p in net.parameters() if p.requires_grad], lr=0.002, weight_decay=0
        )
        acc = 0
        for step in range(STEPS - SINGLE):
            # Both curricula see two real states per update, one root and one later.
            losses = []
            for root in (True, False):
                w, traj = rng.choice(data)
                s, targets = traj[0] if root else rng.choice(traj[1:])
                net.prepare(w)
                m = net.state(w, s)
                selected = rng.choices(targets, k=17)
                scores = {tok: net.token_loss(w, m, tok) for tok in set(selected)}
                losses.extend(scores[tok] for tok in selected)
            loss = torch.stack(losses).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
            opt.step()
            acc += float(loss.detach())
            if (step + 1) % 60 == 0:
                curves.append({"seed": seed, "step": SINGLE + step + 1, "ce": acc / 60})
                acc = 0
        assert initial == fixed_digest(net)
        torch.save(net.state_dict(), dest(a) / f"transfer-{mode}-{seed}.pt")
        sigs = sorted({sig for w, _ in data for sig in digest(w)})
        (dest(a) / f"transfer-{mode}-signatures.json").write_text(json.dumps(sigs))
    (dest(a) / f"transfer-{mode}-curve.json").write_text(json.dumps(curves))


def evaluate_transfer(a):
    models = {}
    for mode, seed in product(("replay", "mixed"), SEEDS):
        net = RoleRead(a, "C")
        net.load_state_dict(
            torch.load(dest(a) / f"transfer-{mode}-{seed}.pt", weights_only=True)
        )
        models[mode, seed] = net.eval()
    held_against = set(
        json.loads((dest(a) / "transfer-mixed-signatures.json").read_text())
    )
    live = []
    diag = []
    for label in ("known", "mixed"):
        ids = (
            product(range(124081, 124084), (0, 1))
            if label == "mixed"
            else product(range(8), (0, 1))
        )
        for i, wire in ids:
            with TemporaryDirectory() as tmp:
                local = copy.copy(a)
                local.out = Path(tmp)
                a0 = next(iter(models.values())).actor
                if label == "mixed":
                    w = mixed(local, a0, i, wire, depth=2)
                    assert held_against.isdisjoint(digest(w))
                else:
                    w = World(
                        a.out
                        / "worlds"
                        / key(
                            (wire, i // 4, i % 2),
                            81011,
                            (0, (i // 2) % 2, 1 - (i // 2) % 2),
                        ),
                        a0,
                    )
                s, ts = native(a, w, teacher="higher")[0]
                for (mode, seed), net in models.items():
                    record = next(
                        x for x in diagnostic(net, w, s, ts) if x["layout"] == "perm0"
                    )
                    diag.append(
                        dict(
                            label=label,
                            case=i,
                            wire=wire,
                            mode=mode,
                            seed=seed,
                            **record,
                        )
                    )
                for draw, block in product((193, 827), (0, 1)):
                    order = list(models)
                    if (i + wire + block + (draw == 827)) % 2:
                        order.reverse()
                    for mode, seed in order:
                        net = models[mode, seed]
                        net.physical = ("held", 0)
                        net.static_cache.clear()
                        with torch.no_grad():
                            result = native(a, w, policy=net, seed=draw)
                        live.append(
                            dict(
                                label=label,
                                case=i,
                                wire=wire,
                                draw=draw,
                                block=block,
                                mode=mode,
                                seed=seed,
                                **result,
                            )
                        )
                for net in models.values():
                    net.static_cache.clear()
    for tag, rows in (("diag", diag), ("native", live)):
        (dest(a) / f"transfer-test-{tag}.json").write_text(
            json.dumps(rows, separators=(",", ":"))
        )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    if a.task == "train":
        transfer(a, os.environ["TRANSFER_MODE"])
    else:
        evaluate_transfer(a)
