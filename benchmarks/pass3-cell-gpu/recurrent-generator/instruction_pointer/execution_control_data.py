"""Native exploration, offline exit forks and masked action credit. No oracle in collection."""

import hashlib
import json
import random
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch
from torch.nn import functional as F

from ccp_v01 import offline_repairs
from credit_scale_buffer import Lane, submit
from discovery_native import configure
from discovery_states import cli, read, save
from discrete_cells import from_q
from discrete_draft import plan
from execution_control import CONTINUE, SEAL, SUBMIT, window
from metal_scaling import models


def effects(rep):
    return sum(rep["ept"]["signed_external"]) + sum(rep["ept"]["signed_internal"])


def exit_audit(binary, program, tape, run, rules=None):
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "fork.json"

        def replay(rows, stop, *flags):
            save(
                path,
                dict(
                    tape,
                    requests=rows,
                    repair_events=[
                        e for e in tape["repair_events"] if e["run"] <= stop
                    ],
                ),
            )
            return json.loads(
                subprocess.check_output(
                    [binary, "replay", program, path, "audit", str(stop), *flags]
                )
            )

        current = [q for q in tape["requests"] if q["run"] <= run]
        prefix = [q for q in current if q["run"] < run]
        exact = replay(prefix, run - 1, "--audit-next-proofs")
        used = {from_q(q) for q in current if q["run"] == run}
        first = max((q["token"] for q in current), default=0) + 1
        extra = [
            dict(q, token=first + i)
            for i, q in enumerate(exact)
            if from_q(q) not in used and (rules is None or q["rule"] in rules)
        ]
        base = replay(current, run, "--ept-origins")
        fork = replay(current + extra, run, "--ept-origins") if extra else base
        before, after = (dict(x["ept"]["origins"]) for x in (base, fork))
        gains = [
            [q["rule"], after[q["token"]]] for q in extra if after.get(q["token"], 0)
        ]
        stable = all(
            before.get(q["token"], 0) == after.get(q["token"], 0) for q in current
        ) and sum(g for _, g in gains) == effects(fork) - effects(base)
        return {
            "run": run,
            "options": len(exact),
            "additions": len(extra),
            "credited": gains if stable else None,
            "before": effects(base),
            "after": effects(fork),
            "base_hash": base["state_sha"],
            "fork_hash": fork["state_sha"],
        }


@torch.no_grad()
def collect(a):
    corpus = read(a.previous / "corpus.json")
    for idx in range(a.programs):
        dest = a.out / f"experience/{idx}.json"
        if dest.exists():
            continue
        lane = Lane(a, idx, 2, corpus[idx]["signature"])
        history = []
        try:
            _, _, page = configure(
                a, lane.m, "D", a.cap, lambda *args, page=lane.page: (None, None, page)
            )
            balance = 0
            rng = random.Random(idx + 8301)
            lane.advance()
            while not lane.done:
                frame = lane.frame
                lane.m.update(frame)
                balance = min(6, balance + 2)

                if a.shuffle_prefix and frame["run"] <= 1 + idx % 3:
                    r = frame["run"]
                    prefix = list(lane.client.offline_tape(r - 1))
                    candidates = lane.replay(prefix, r - 1, "--audit-next-proofs")
                    rng.shuffle(candidates)
                    selected = candidates[: rng.randint(0, len(candidates))]
                    width = rng.choice((1, 4, 16))
                    responses = submit(lane.client, list(map(from_q, selected)), width)
                    history.append(
                        {
                            "run": r,
                            "epoch": frame["epoch"],
                            "updated": len(frame["updates"]),
                            "reason": "teacher_prefix",
                            "actions": [],
                            "selected": selected,
                            "responses": responses,
                            "width": width,
                        }
                    )
                    lane.client.seal()
                    lane.advance()
                    continue

                def draw(lane=lane, page=page):
                    return [
                        item.cell
                        for item in page.sample(lane.m, (), 1, lane.rng, Counter())
                    ]

                def issue(cells, lane=lane):
                    replies = submit(lane.client, cells, 256)
                    items = plan(cells)
                    lane.m.observe_reply(items, dict(enumerate(replies)))
                    return replies

                def choose(x, mask, rng=rng):
                    return rng.choices(
                        range(3), [p * b for p, b in zip((5, 5, 1), mask)], k=1
                    )[0]

                rows, balance, reason = window(
                    lane.m, balance, "C", choose, draw, issue, float("inf"), True
                )
                history.append(
                    {
                        "run": frame["run"],
                        "actions": rows,
                        "reason": (
                            "exploration_seal" if reason == "neural_seal" else reason
                        ),
                        "updated": len(frame["updates"]),
                        "epoch": frame["epoch"],
                    }
                )
                lane.client.seal()
                lane.advance()
            tape = {
                "schema": "cell-token-replay/v2",
                "program_sha256": lane.program_sha,
                "requests": list(lane.client.offline_tape(history[-1]["run"])),
                "repair_events": list(offline_repairs(lane.repairs)),
            }
            rep = lane.replay(tape["requests"], history[-1]["run"], "--ept-origins")
            assert rep["state_sha"] == lane.terminal["state_sha"]
            origins = dict(rep["ept"]["origins"])
            # Named use of an accepted request in a later actually productive request.
            used = {
                p["address"]["token"]
                for q in tape["requests"]
                if origins.get(q["token"], 0)
                for p in q["parents"]
            }
            for event in history:
                event["exit"] = exit_audit(
                    a.runtime_binary, lane.program, tape, event["run"]
                )
                for row in event["actions"]:
                    ids = row.get("ids", [])
                    row["ops"] = sum(origins.get(i, 0) for i in ids)
                    row["later_used"] = sum(i in used for i in ids)
            save(
                dest,
                {
                    "behavior": "randomized_controls_frozen_neural_cells",
                    "idx": idx,
                    "signature": lane.signature,
                    "checkpoint_sha256": hashlib.sha256(
                        a.checkpoint.read_bytes()
                    ).hexdigest(),
                    "exploration_seed": idx + 8301,
                    "rollout_seed": lane.seed,
                    "tape": tape,
                    "history": history,
                },
            )
        finally:
            lane.close()
        print("native collection", idx, len(history), flush=True)


def supervision(events):
    """Prefer witnessed choices. A zero-gain accepted request has unknown future value."""
    for e in events:
        omission = e["exit"]["credited"]
        future_submit = None
        for row in reversed(e["actions"]):
            a = row["action"]
            target = None
            if a == SEAL:
                if omission:
                    target = CONTINUE
            elif a == SUBMIT:
                future_submit = row
                if row["ops"] or row["later_used"]:
                    target = SUBMIT
            elif future_submit:
                if future_submit["ops"] or future_submit["later_used"]:
                    # Batch-level evidence only; no positive labels on individual addresses.
                    target = CONTINUE
                elif (
                    row["draft"] == 0
                    and omission == []
                    and future_submit["status"]
                    and all(s in (1, 2) for s in future_submit["status"])
                ):
                    target = SEAL
            if target is not None and row["mask"][target] and sum(row["mask"]) > 1:
                yield row["x"], row["mask"], target, a == SEAL and bool(omission)


def train(a):
    torch.manual_seed(a.seed)
    rates = models("1M")[1]
    rates.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[1]
    )
    train, held = [], []
    signatures = [set(), set()]
    for idx in range(a.programs):
        shards = [read(a.out / f"experience/{idx}.json")]
        if a.extra_experience:
            shards.append(read(a.extra_experience / f"experience/{idx}.json"))
        split = int(idx >= a.programs * 3 // 4)
        for sh in shards:
            signatures[split].add(sh["signature"])
            (held if split else train).extend(supervision(sh["history"]))
    assert signatures[0].isdisjoint(signatures[1])

    def tensors(rows):
        f, m, y, early = zip(*rows)
        return torch.tensor(f), torch.tensor(m), torch.tensor(y), torch.tensor(early)

    x, mask, y, early = tensors(train)
    ht, hm, hy, _ = tensors(held)
    opt = torch.optim.AdamW(rates.parameters(), lr=0.0002)
    tick = perf_counter()
    for _ in range(160):
        i = torch.randint(len(y), (64,))
        logits = rates(x[i]).masked_fill(~mask[i], -1e9)
        if a.no_exit_credit:
            loss = (
                F.cross_entropy(logits, y[i], reduction="none")
                .masked_fill(early[i], 0)
                .mean()
            )
        else:
            loss = F.cross_entropy(logits, y[i])
        opt.zero_grad()
        loss.backward()
        opt.step()

    def score(x, m, y):
        pred = rates(x).masked_fill(~m, -1e9)
        return {
            "n": len(y),
            "counts": torch.bincount(y, minlength=3).tolist(),
            "loss": float(F.cross_entropy(pred, y).detach()),
            "correct": int((pred.argmax(1) == y).sum()),
        }

    suffix = "-no-exit-credit" if a.no_exit_credit else ""
    if a.extra_experience:
        suffix += "-shuffle"
    torch.save(rates.state_dict(), a.out / f"rates{suffix}.pt")
    save(
        a.out / f"fit{suffix}.json",
        {
            "exit_labels": int(early.sum()),
            "train": score(x, mask, y),
            "held": score(ht, hm, hy),
            "seconds": perf_counter() - tick,
            "seed": a.seed,
            "updates": 160,
        },
    )


def arguments():
    p = cli()
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--programs", type=int, default=16)
    p.add_argument("--shuffle-prefix", action="store_true")
    p.add_argument("--extra-experience", type=Path)
    p.add_argument("--cap", type=int, default=16)
    p.add_argument("--no-exit-credit", action="store_true")
    p.add_argument("--seed", type=int, default=8301)
    return p


if __name__ == "__main__":
    p = arguments()
    p.add_argument("mode", choices=["collect", "train"])
    a = p.parse_args()
    a.pages = 6
    a.generation_seed = 536
    (a.out / "experience").mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    (collect if a.mode == "collect" else train)(a)
