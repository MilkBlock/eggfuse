"""Program-held-out complete-token training with optional messages from unbound roles."""

import json
import math
import os
import pickle
import random
from collections import Counter
from time import perf_counter
from types import MethodType

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_world import folder as foundation_folder
from foundation_world import world
from joint_cell_corpus import folder, read_rows
from operand_read_model import words
from partner_index_worlds import args
from prefix_attention import static_wires
from prefix_corpus import folder as old
from prefix_train import CASES, make


def feedback(n):
    previous = n.address

    def address(self, w, m, tid, prefix):
        lp = previous(w, m, tid, prefix)
        rid = w.layouts[tid][0][0]
        j = len(prefix)
        if lp is None or len(w.roles[rid]) < 3 or j + 1 >= len(w.roles[rid]):
            return lp
        cache = m.setdefault("future_support", {})
        if (rid, j) not in cache:
            extra = lp.new_zeros(lp.shape)
            for k in range(j + 1, len(w.roles[rid])):
                links = [
                    (src, col, node)
                    for prev, src, col, node in static_wires(w, rid, k)
                    if prev == j
                ]
                if not links:
                    continue
                rows = (m["tables"] == w.roles[rid][k]).nonzero().flatten()
                if not len(rows):
                    continue
                if "prefix_bits" not in m:
                    m["prefix_bits"] = words([p[4] for p in m["ports"]])[0].reshape(
                        len(lp), -1, 2, 32
                    )
                bits = m["prefix_bits"]
                src, col, node = zip(*links, strict=True)
                role = self.cache[0][list(node)][:, None, :]
                v = self.actor.latent(bits[rows][:, list(col)]).tanh()
                v = v + 0.25 * self.actor.input_content(v + role).tanh()
                q = self.actor.query(m["ctx"] + role).tanh()
                scale = math.sqrt(64 * len(links))
                weight = ((q * v).sum((1, 2, 3)) / scale).softmax(0)
                pooled = (v * weight[:, None, None, None]).sum(0)
                if getattr(self, "audit_future", False):
                    m.setdefault("future_probes", []).append((j, k, pooled))
                u = self.actor.latent(bits[:, list(src)]).tanh()
                u = u + 0.25 * self.actor.query(u + role).tanh()
                extra = extra + (u * pooled).sum((1, 2, 3)) / scale
            cache[rid, j] = extra
        return (lp + cache[rid, j]).log_softmax(0)

    n.address = MethodType(address, n)
    return n


def build(a, held, n):
    groups = {"branch": [], "teacher": [], "autonomous": [], "foundation": []}
    for case in CASES:
        if case == held:
            continue
        w = World(egg(a, case)[0], n.actor, entry_table=None, sides="")
        for s, r, ts, _ in pickle.loads((old(a) / f"{case}.pkl").read_bytes()):
            if ts:
                groups["branch"].append((w, s, [(r, t) for t in ts]))
        for src in ("teacher", "autonomous"):
            groups[src].extend(
                (w, s, t) for s, t in read_rows(folder(a) / f"{case}-{src}.pkl.gz")
            )
    for i in range(12):
        w = world(a, n.actor, i, True, "multi")
        audited = dict(
            (s["run"], (s, t))
            for s, t in pickle.loads(
                (foundation_folder(a) / f"states-multi-1-{i}.pkl").read_bytes()
            )
        )
        for s, _ in native(
            a, w, teacher="primitive", rule_state=True, receipt_memory=True
        ):
            if s["run"] in audited:
                original, t = audited[s["run"]]
                assert {
                    k: v for k, v in s.items() if k not in ("rule_state", "check_dirty")
                } == original
                groups["foundation"].append((w, s, t))
    return groups


def legacy_examples(a, n):
    rows = []
    for z in json.loads((folder(a) / "legacy.json").read_text()):
        dest = folder(a) / f"legacy-{z['idx']}"
        w = World(dest, n.actor, entry_table=None, sides="")
        rows.extend((w, s, ts) for s, ts in read_rows(dest / "rows.pkl.gz"))
    return rows


def fitted(a, case, arm, seed):
    n = make(a, "rel")
    if arm == "feedback":
        feedback(n)
    if seed:
        weights = torch.load(folder(a) / f"{case}-{arm}-{seed}.pt", weights_only=True)
        assert set(weights) == {k for k, p in n.named_parameters() if p.requires_grad}
        n.load_state_dict(weights, strict=False)
    return n.eval()


def train(a, held):
    shell = make(a, "rel")
    groups = build(a, held, shell)
    if "replay" in os.getenv("JC_TRAIN_ARMS", "").split():
        groups["legacy"] = legacy_examples(a, shell)
    for seed in (71, 113):
        for arm in os.getenv("JC_TRAIN_ARMS", "expanded feedback small").split():
            dest = folder(a) / f"{held}-{arm}-{seed}"
            if dest.with_suffix(".json").exists():
                continue
            n = fitted(a, held, arm, 0)
            n.grouped_training_reduction = True
            opt = torch.optim.AdamW(
                [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
            )
            rng = random.Random(seed)
            counts = Counter()
            exposed = set()
            states = set()
            curve = []
            g = Counter()
            start = perf_counter()
            acc = 0.0
            for j in range(512):
                src = (
                    rng.choices(
                        ["branch", "teacher", "autonomous", "foundation", "legacy"],
                        [2, 3, 1, 2, 2],
                    )[0]
                    if arm == "replay"
                    else rng.choices(
                        ["branch", "teacher", "autonomous", "foundation"], [2, 5, 1, 2]
                    )[0]
                    if arm != "small"
                    else "branch"
                )
                i = rng.randrange(len(groups[src]))
                w, s, ts = groups[src][i]
                t = rng.choice(ts)
                counts[src] += 1
                exposed.add((src, i, t))
                states.add((src, i))
                n.prepare(w)
                m = n.state(w, s)
                loss = n.token_loss(w, m, t)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                for k, p in n.named_parameters():
                    if p.grad is not None:
                        g[k] += float(p.grad.norm()) / 512
                torch.nn.utils.clip_grad_norm_(n.parameters(), 2.0)
                opt.step()
                acc += float(loss.detach())
                if j % 64 == 63:
                    curve.append(acc / 64)
                    acc = 0.0
            torch.save(
                {k: p.detach() for k, p in n.named_parameters() if p.requires_grad},
                dest.with_suffix(".pt"),
            )
            dest.with_suffix(".json").write_text(
                json.dumps(
                    dict(
                        curve=curve,
                        gradient=g,
                        source_exposures=counts,
                        states=len(states),
                        targets=len(exposed),
                        seconds=perf_counter() - start,
                    )
                )
            )
            print(held, arm, seed, curve, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(args(), os.environ["TR_CASE"])
