"""Reuse the existing stop logit in the unsigned decoder; native actions remain Cells."""

import hashlib
import json
import os
import pickle
from collections import Counter
from time import perf_counter

import torch
from torch.nn import functional as F

from cell_kv_runtime import native
from competition_draw import Page
from constructible_study import TracePolicy
from foundation_fit import model
from foundation_wake import world as wake_world
from foundation_world import folder, world
from partner_index_worlds import args
from trigger_training import directory as previous


def directory(a):
    d = a.out / "variable-completion"
    d.mkdir(exist_ok=True)
    return d


def network(a, seed):
    n = model(a, seed, 32)
    n.load_state_dict(torch.load(previous(a) / f"both-{seed}.pt", weights_only=True))
    n.rule_condition = "both"
    n.eval()
    n.physical = ("held", 0)
    return n


def boundary_input(m):
    # Use the decoder's own family probabilities. Do not recompute feasibility or trigger.
    js = [positions[0] for positions in m["families"].values()]
    return m["ctx"] + m["root_lp"].exp() @ m["score_codes"][js]


def label(w, s, targets):
    if targets:
        return "cell"
    domains = {p[3] for p in s["ports"]}
    constructible = {
        w.layouts[t][0][0]
        for t in s["menu"]
        if all(x in domains for x in w.roles[w.layouts[t][0][0]])
    }
    if (
        s["check_dirty"]
        and constructible
        and all(not s["rule_state"][r][1] for r in constructible)
    ):
        return "end"
    return "unknown"


def examples(a, n, train):
    rows = []
    counts = Counter()

    def add(w, s, ts):
        kind = label(w, s, ts)
        counts[kind] += 1
        if kind == "unknown":
            return
        n.prepare(w)
        m = n.state(w, s)
        value = boundary_input(m)
        ce = sum(float(n.token_loss(w, m, t)) for t in ts) / max(1, len(ts))
        rows.append((value, kind == "end", ce))

    for i in range(12 if train else 6):
        for distinct, tag in ((False, "wake"), (True, "wake-asym")):
            w = wake_world(a, n.actor, i, train, distinct)
            obs = pickle.loads((folder(a) / f"{tag}-{train}-{i}.pkl").read_bytes())
            seen = set()
            for o in obs:
                for s, flags, items in o["states"]:
                    # The archived producer requires check_dirty=true and exact native
                    # frame alignment for these observations (foundation_wake.samples).
                    snap = dict(s, rule_state=flags, check_dirty=True)
                    key = hashlib.sha256(pickle.dumps(snap)).digest()
                    if key in seen:
                        continue
                    seen.add(key)
                    ts = [t for t, _, g in items if g]
                    if label(w, snap, ts) == "end":
                        assert items and all(
                            why == "untriggered_rule" for _, why, _ in items
                        )
                    add(w, snap, ts)
        if train or i < 4:
            w = world(a, n.actor, i, train, "multi")
            audited = {
                s["run"]: (s, ts)
                for s, ts in pickle.loads(
                    (folder(a) / f"states-multi-{int(train)}-{i}.pkl").read_bytes()
                )
            }
            for s, _ in native(
                a, w, teacher="primitive", rule_state=True, receipt_memory=True
            ):
                if s["run"] in audited:
                    original, ts = audited[s["run"]]
                    assert {
                        k: v
                        for k, v in s.items()
                        if k not in ("rule_state", "check_dirty")
                    } == original
                    add(w, s, ts)
    return (
        torch.stack([v for v, _, _ in rows]),
        torch.tensor([b for _, b, _ in rows]).float(),
        torch.tensor([ce for _, _, ce in rows]),
        counts,
    )


def train_model(a, seed):
    n = network(a, seed)
    n.requires_grad_(False)
    head = n.actor.stop.requires_grad_(True)
    with torch.no_grad():
        x, y, ce, counts = examples(a, n, True)
        hx, hy, hce, test_counts = examples(a, n, False)
    opt = torch.optim.AdamW(head.parameters(), lr=0.02, weight_decay=0.0)
    rng = torch.Generator().manual_seed(seed)
    out = directory(a)
    curve = []
    for step in range(1025):
        if step in (0, 64, 256, 1024):
            with torch.no_grad():
                logits = head(hx).flatten()
                probs = logits.sigmoid()
                curve.append(
                    {
                        "step": step,
                        "p_end_if_end": float(probs[hy == 1].mean()),
                        "p_end_if_verified": float(probs[hy == 0].mean()),
                        "held_ce": float(
                            (
                                F.binary_cross_entropy_with_logits(
                                    logits, hy, reduction="none"
                                )
                                + hce
                            ).mean()
                        ),
                    }
                )
        if step == 1024:
            break
        ix = torch.randint(len(y), (64,), generator=rng)
        # Joint CE of END or a complete Cell. Conditional Cell logits are frozen
        # for this readout-only experiment, so their CE can be cached exactly.
        loss = (
            F.binary_cross_entropy_with_logits(head(x[ix]).flatten(), y[ix])
            + ce[ix].mean()
        )
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
    torch.save(head.state_dict(), out / f"boundary-{seed}.pt")
    (out / f"training-{seed}.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "counts": counts,
                "held": test_counts,
                "curve": curve,
                "parameters": sum(p.numel() for p in head.parameters()),
            }
        )
    )


class CompletionPolicy(TracePolicy):
    def __init__(self, n, unique, slot_limit, variable):
        super().__init__(n, unique, slot_limit)
        self.variable = variable

    def generate(self, w, s, rng, slots):
        start = perf_counter()
        if self.slot_limit is not None:
            slots = min(slots, self.slot_limit - self.count["offered"])
        if not slots:
            return []
        self.count["offered"] += slots
        cells = []
        self.count["opportunities"] += 1
        if s["menu"]:
            page = Page(self.net, w, s)
            self.count["state_encodes"] += 1
            end = None
            if self.variable and page.m.get("has_complete_domain", True):
                end = float(
                    self.net.actor.stop(boundary_input(page.m)).sigmoid().item()
                )
                self.count["boundary_readouts"] += 1
            draws = page.draws(rng, slots, self.unique, end)
            cells = [t for t in draws if t is not None]
            self.count["distribution_reads"] += page.net_calls
            self.count["sampled_end"] += int(getattr(page, "ended", False))
        self.count[f"length_{len(cells)}"] += 1
        self.count["signed"] += len(cells)
        self.decode_s += perf_counter() - start
        return cells


if __name__ == "__main__":
    torch.set_num_threads(1)
    train_model(args(), int(os.getenv("TR_SEED", "71")))
