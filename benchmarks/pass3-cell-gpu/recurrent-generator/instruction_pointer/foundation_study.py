"""Shared publication memory, native-target completion CE and independent EggCC execution."""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from binding_egg import execute
from binding_model import read_packet
from completion_context import read
from discrete_draft import Cell
from first_parent import records
from foundation_completion import Completion
from head_joint_egg import parent_policy
from multirule_support import chooser
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_coverage import Target
from recursive_train import folder

CASES = ("fact", "loopfact", "sum-divisors")
BASE = Path(
    os.environ.get(
        "MULTIRULE_OUT", "/Volumes/Extreme SSD/eggfuse-experiments/multi-association"
    )
)


def directory(a, case):
    if case.startswith("dynamic-"):
        return a.previous / "programs" / f"{int(case.split('-')[1]):04d}"
    return folder(a.data, case.removeprefix("rollout-"))


@torch.no_grad()
def prepare(a):
    model = frozen(a, a.seeds[0])
    out = a.out / "data"
    out.mkdir(parents=True, exist_ok=True)
    for source in sorted((BASE / "corpus").glob("*/examples.pkl")):
        name = source.parent.name
        d = directory(a, name)
        prog = read(d / "program.json")
        memory = conditioned(a, d, source.parent / "observer")
        decoder = Completion(model, "evidence", "cpu")
        grouped = defaultdict(list)
        for row in read_packet(source):
            grouped[row["run"]].append(row)
        rng = np.random.default_rng(761)
        selected = set(
            rng.choice(
                sorted(grouped),
                min(len(grouped), 8 if name.startswith("dynamic") else 16),
                replace=False,
            )
        )
        items = []
        stats = Counter()
        try:
            for line in (source.parent / "frames").open():
                frame = json.loads(line)
                if frame.get("final_publication"):
                    continue
                memory.update(frame)
                decoder.publish(memory, prog, frame, stats)
                r = frame["run"]
                if r not in selected:
                    continue
                for row in grouped[r]:
                    for k in rng.choice(
                        len(row["g"]), min(2, len(row["g"])), replace=False
                    ):
                        gold = row["g"][k]
                        refs = tuple(
                            row["z"]["addrs"][j][i] for j, i in enumerate(gold)
                        )
                        cell = Cell(row["rid"], refs)
                        items.append(
                            (name, r, len(decoder.mem.rows), cell, decoder.paths(cell))
                        )
        finally:
            memory.close_observer()
        torch.save(items, out / (name + ".pt"))
        print(name, len(items), stats, flush=True)


def packet_loss(net, items, mode, device):
    # Marginalize all ordered construction routes of the verified COMPLETE token.
    factors = [[], []]
    paths = []
    for *_, all_paths in items:
        selected = all_paths if mode == "evidence" else [all_paths[0]]
        current = []
        for path in selected:
            ids = []
            for c, y in path:
                if mode == "rule" and c.entry:
                    continue
                idx = len(factors[c.kind])
                factors[c.kind].append((c, y))
                ids.append((c.kind, idx))
            current.append(ids)
        paths.append(current)
    probs = []
    for group in factors:
        if not group:
            probs.append(None)
            continue
        sizes = [len(c.keys) for c, _ in group]
        keys = torch.cat([c.keys for c, _ in group]).to(device)
        queries = torch.cat([c.q.expand_as(c.keys) for c, _ in group]).to(device)
        bias = torch.cat([c.bias for c, _ in group]).to(device)
        from address_scores import mlp

        kind = group[0][0].kind
        layer = net.scorer if kind else net.gate
        zero = torch.zeros_like(keys)
        scores = (
            mlp(layer, queries, zero, keys, kind)
            - mlp(layer, queries, keys, zero, kind)
        ) * 0.5 + bias
        start = np.cumsum([0] + sizes[:-1])
        pos = np.arange(max(sizes))[None, :]
        mask = pos < np.asarray(sizes)[:, None]
        gather = torch.as_tensor(np.where(mask, start[:, None] + pos, 0), device=device)
        norm = (
            scores[gather]
            .masked_fill(~torch.as_tensor(mask, device=device), -torch.inf)
            .logsumexp(1)
        )
        target = torch.as_tensor(
            start + np.asarray([y for _, y in group]), device=device
        )
        probs.append(scores[target] - norm)
    # One Recipe route plus one route per external role, including nullary Cells.
    flat = (
        torch.cat([v for v in probs if v is not None])
        if any(v is not None for v in probs)
        else next(net.parameters()).new_zeros(1)
    )
    ix = []
    owners = []
    for token in paths:
        loc = []
        for terms in token:
            loc.append(len(ix))
            ix.append([i + (len(factors[0]) if k else 0) for k, i in terms])
        owners.append(loc)

    def padded(rows):
        n = max(1, max(map(len, rows)))
        ab = np.zeros((len(rows), n), np.int64)
        mask = np.zeros_like(ab, dtype=bool)
        for i, ids in enumerate(rows):
            ab[i, : len(ids)] = ids
            mask[i, : len(ids)] = 1
        return torch.as_tensor(ab, device=device), torch.as_tensor(mask, device=device)

    ab, mask = padded(ix)
    logpaths = flat[ab].masked_fill(~mask, 0).sum(-1)
    ab, mask = padded(owners)
    return -logpaths[ab].masked_fill(~mask, -torch.inf).logsumexp(-1).mean()


def train(a):
    data = [
        x
        for f in sorted((a.out / "data").glob("*.pt"))
        for x in torch.load(f, weights_only=False, map_location="cpu")
    ]
    device = "mps"
    rows = []
    for case in CASES:
        held = [x for x in data if x[0].removeprefix("rollout-") == case]
        tr = [x for x in data if x[0].removeprefix("rollout-") != case]
        cuts = np.quantile([x[2] for x in tr], [0.2, 0.6])
        for mode in ("rule", "evidence"):
            net = frozen(a, a.seeds[0]).local.base.to(device)
            net.requires_grad_(False)
            for part in (net.gate, net.scorer):
                part.requires_grad_(True)
            opt = torch.optim.Adam(
                [p for p in net.parameters() if p.requires_grad], lr=0.0007
            )
            rng = np.random.default_rng(9633)
            for step in range(241):
                if step in (0, 80, 240):
                    with torch.no_grad():
                        nll = sum(
                            float(packet_loss(net, held[k : k + 4], mode, device))
                            * len(held[k : k + 4])
                            for k in range(0, len(held), 4)
                        ) / len(held)
                    rows.append(
                        {
                            "case": case,
                            "mode": mode,
                            "updates": step,
                            "exposures": 4 * step,
                            "train": len(tr),
                            "held": len(held),
                            "held_ce": nll,
                        }
                    )
                    print(rows[-1], flush=True)
                if step == 240:
                    break
                pool = [
                    i
                    for i, x in enumerate(tr)
                    if step >= 100 or x[2] <= cuts[int(step >= 40)]
                ]
                ex = [tr[i] for i in rng.choice(pool, 4, replace=False)]
                loss = packet_loss(net, ex, mode, device)
                opt.zero_grad()
                if not loss.requires_grad:
                    continue  # Complete singleton domains have log probability zero.
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
                opt.step()
            torch.save(
                {"gate": net.gate.state_dict(), "scorer": net.scorer.state_dict()},
                a.out / f"{case}-{mode}.pt",
            )
            records(a.out / "training.csv", rows)


def network(a, case, arm):
    model = frozen(a, a.seeds[0])
    mode = "evidence" if "evidence" in arm else "rule"
    dec = Completion(
        model,
        mode,
        os.environ.get("FOUNDATION_DEVICE", "mps"),
        relation="no-field" not in arm,
    )
    if arm.startswith("prior"):
        model.load_state_dict(
            torch.load(BASE / f"{case}-ce-count.pt", weights_only=True)
        )
    if arm.startswith("ce"):
        state = torch.load(
            a.out / f"{case}-{mode}.pt", map_location=dec.device, weights_only=True
        )
        dec.net.gate.load_state_dict(state["gate"])
        dec.net.scorer.load_state_dict(state["scorer"])
    if arm == "ce-evidence-force-rule":
        dec.mode = "rule"
    return dec


@torch.no_grad()
def live(a):
    a.slots = 8
    for case in CASES:
        d = folder(a.data, case)
        rt = a.out / case
        rt.mkdir(exist_ok=True)
        target = Target(read(d / "program.json"), read(BASE / case / "ref.json"))
        ref = target, target.match(read(BASE / case / "init.json"))
        arms = os.environ.get(
            "FOUNDATION_ARMS", "frozen-rule,frozen-evidence,ce-rule,ce-evidence"
        ).split(",")
        seed = int(os.environ.get("DRAW", "9734"))
        for block in range(int(os.environ.get("BLOCKS", "2"))):
            for arm in arms if block % 2 == 0 else arms[::-1]:
                dec = network(a, case, arm)
                dest = rt / f"{arm}-{seed}-{block}"
                audit = os.environ.get("FOUNDATION_AUDIT") == "1"
                cap = os.environ.get("FOUNDATION_CAP") == "1"
                if audit or cap:
                    dest = dest.with_name(("audit-" if audit else "cap-") + dest.name)
                slot_limit = int(os.environ.get("FOUNDATION_SLOTS", "0")) or None
                if slot_limit is not None:
                    dest = dest.with_name(f"slots{slot_limit}-" + dest.name)
                policies = {"page_policy": dec}
                if arm == "prior-index":
                    mdl = frozen(a, a.seeds[0])
                    mdl.load_state_dict(
                        torch.load(BASE / f"{case}-ce-count.pt", weights_only=True)
                    )
                    policies = {
                        "parent_policy": parent_policy(mdl, "joint"),
                        "template_policy": chooser(mdl, "ce-count"),
                    }
                execute(
                    a,
                    d,
                    dest,
                    dec.net,
                    arm,
                    9633,
                    block,
                    seed,
                    ref,
                    address_seed=179636 + seed - 9734,
                    audit_slots=audit,
                    slot_limit=slot_limit,
                    paid_limit={"fact": 541, "loopfact": 745, "sum-divisors": 742}[case]
                    if cap
                    else None,
                    **policies,
                )
                r = read(dest / "result.json")
                print(
                    case, arm, r["covered"], r["ops"], r["stats"], r["wall"], flush=True
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"prepare": prepare, "train": train, "live": live}[a.task](a)
