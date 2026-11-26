"""Fit the existing coverage objective from native shards, drawing fresh policy samples."""

import gzip
import hashlib
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch

from address_scores import weight
from cell_transaction import STATUS
from coverage_fit import BUDGETS
from coverage_onpolicy import coverage_gradient, freeze
from credit_scale_programs import directory
from discovery_sampling import Domain
from discovery_score import token
from discovery_states import cli, read, save
from discrete_cells import from_q
from query_environment import conditioned, setup

ARMS = (
    "teacher",
    "self",
    "omission",
    "duplicate",
    "failure",
    "shuffle",
    "downstream",
    "mixed",
)


def downstream(positive):
    """Conserve one unit per successful signature across immediate evidenced parents."""
    weights = Counter({i: 1.0 for i in positive})
    for i, cell in positive.items():
        parents = {owner for owner, _, _ in cell.refs if owner in positive}
        if parents:
            weights[i] -= 0.5
            for parent in parents:
                weights[parent] += 0.5 / len(parents)
    assert abs(sum(weights.values()) - len(positive)) < 1e-7
    return weights


def online_marginal(executed, extra, failed, weights, arm):
    level = ARMS.index(arm)
    positives = executed | (extra if level >= 2 else set())

    def value(items):
        n = Counter(items)
        return [
            (weights.get(c, 1.0) if level >= 6 else 1.0)
            * int(c in positives and n[c] == 1)
            - int(level >= 3 and n[c] > 1)
            - int(level >= 4 and c in failed)
            for c in items
        ]

    return {c: c for c in positives}, value if level >= 3 else None


def load_shard(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


@torch.no_grad()
def states(a, idx, source, shard_path, gate_cfg):
    d = directory(a, idx)
    with tempfile.TemporaryDirectory() as td:
        obs = Path(td) / "scheduler"
        if source == "teacher":
            import os

            result = json.loads(
                subprocess.check_output(
                    [
                        a.runtime_binary,
                        "replay",
                        d / "program.json",
                        d / "teacher.json",
                        "audit",
                        "--memory",
                        os.devnull,
                        "--ept-origins",
                    ],
                    env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(obs)),
                )
            )
            qs = read(d / "teacher.json")["requests"]
            gains = dict(result["ept"]["origins"])
            pos = {q["token"]: from_q(q) for q in qs if gains.get(q["token"], 0) > 0}
            w = downstream(pos)
            by = defaultdict(dict)
            for q in qs:
                i = q["token"]
                if i in pos:
                    by[q["run"]][pos[i]] = w[i]
            with (d / "memory.jsonl").open() as f:
                frames = list(map(json.loads, f))
            examples = [
                (f, None, set(by[f["run"]]), set(), set(), by[f["run"]]) for f in frames
            ]
        else:
            shard = load_shard(shard_path)
            obs.write_text("".join(json.dumps(x) + "\n" for x in shard["scheduler"]))
            g = dict(shard["origins"])
            pos = {}
            for e in shard["events"]:
                for k, v in (
                    ("generated", "response"),
                    ("assisted", "assisted_response"),
                ):
                    for c, res in zip(e[k], e[v], strict=True):
                        if g.get(res[0], 0) > 0:
                            pos[res[0]] = token(c)
            w = downstream(pos)
            examples = []
            for e in shard["events"]:
                observed = {}
                failed = set()
                for raw, reply, gain in zip(
                    e["generated"], e["response"], e["signed_gain"], strict=True
                ):
                    c = token(raw)
                    if gain:
                        observed[c] = w.get(reply[0], 1.0)
                    if STATUS[reply[1]] in ("untriggered_rule", "binding", "guard"):
                        failed.add(c)
                if set(observed) & failed:
                    raise ValueError("conflicting same-publication failure")
                examples.append(
                    (
                        e["frame"],
                        e["context"],
                        set(observed),
                        {token(c) for c, _ in e["omitted"]},
                        failed,
                        observed,
                    )
                )
        m = conditioned(a, d, obs)
        m.page = setup(gate_cfg, m, "D", 256)[2]
        try:
            for f, ctx, ex, om, bad, w in examples:
                m.update(f)
                if ctx is not None:
                    torch.testing.assert_close(
                        m.context(), torch.tensor(ctx), atol=0, rtol=0
                    )
                if m.ids and Domain(m).size:
                    yield freeze(m), ex, om, bad, w
        finally:
            m.close_observer()


def train(a):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    bank = defaultdict(list)
    for p in sorted((a.out / "buffer").glob("*.json.gz")):
        idx, b, _ = p.name.split("-", 2)
        key = int(idx), int(b)
        bank[key].append(p)
    if any((i, 2) not in bank and (i, 0) not in bank for i in range(a.programs)):
        raise ValueError("incomplete nested dataset")
    gate = weight(a).to("mps").eval()
    nets = {}
    for arm in a.arms:
        for seed in a.seeds:
            name = f"{arm}-n{a.programs}-u{a.updates}"
            dest = a.out / "weights" / str(seed)
            dest.mkdir(exist_ok=True, parents=True)
            if (dest / (name + ".pt")).exists():
                continue
            net = weight(a).to("mps")
            net.load_state_dict(torch.load(a.initial, weights_only=True))
            nets[arm, seed] = (
                net,
                torch.optim.AdamW(net.parameters(), lr=0.00015),
                np.random.default_rng(seed + 2),
                [],
                dest / name,
            )
    if not nets:
        return
    start = perf_counter()
    # Common program / run / budget schedule for all interventions and fit seeds.
    order = np.random.default_rng(607).permutation(a.programs)
    repeat = max(1, a.updates // a.programs)
    step = 0
    for group in range(a.updates):
        idx = int(order[group % len(order)])
        seq = np.random.default_rng(7921 + group)
        pool = {}
        required = {"teacher"}
        if any(arm != "teacher" for arm, _ in nets):
            required.add(0)
        if any(arm in ("shuffle", "downstream", "mixed") for arm, _ in nets):
            required.add(1)
        if any(arm == "mixed" for arm, _ in nets):
            required.add(2)
        for src in sorted(required, key=str):
            if src == "teacher" or (idx, src) in bank:
                paths = bank.get((idx, src), ())
                # Pick a recorded behavior policy without consuming the optimizer RNG.
                shard_path = (
                    paths[int(seq.integers(len(paths)))]
                    if len(paths) > 1
                    else next(iter(paths), None)
                )
                pool[src] = list(states(a, idx, src, shard_path, cfg))
        for local in range(repeat):
            if step == a.updates:
                break
            # Use one matched stratum for each step, with counterbalanced source.
            ordinal = (local + group) % max(1, len(pool["teacher"]))
            b = int(seq.choice(BUDGETS))
            for (arm, seed), (net, opt, rng, hist, path) in nets.items():
                src = (
                    "teacher"
                    if arm == "teacher" or step % 2 == 0
                    else (
                        1
                        if arm in ("shuffle", "downstream", "mixed") and step % 4 == 3
                        else 0
                    )
                )
                if arm == "mixed" and step % 8 in (1, 5):
                    src = 2
                if arm == "mixed" and src not in pool:
                    src = 2
                records = pool[src]
                if not records:
                    raise ValueError((idx, src, "empty training state bank"))
                m, ex, om, bad, w = records[ordinal % len(records)]
                credit, margin = online_marginal(ex, om, bad, w, arm)
                loss, hits, slots, draws = coverage_gradient(
                    net, m, credit, gate, b, rng, marginal=margin
                )
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    net.parameters(), 5, error_if_nonfinite=True
                )
                opt.step()
                hist.append((idx, src, ordinal % len(records), b, hits, slots, draws))
            step += 1
        del pool
        if step == a.updates:
            break
    torch.mps.synchronize()
    seconds = perf_counter() - start
    for (arm, seed), (net, opt, rng, hist, path) in nets.items():
        torch.save(net.cpu().state_dict(), path.with_suffix(".pt"))
        save(
            path.with_suffix(".json"),
            {
                "arm": arm,
                "seed": seed,
                "history": hist,
                "group_seconds": seconds,
                "group_arms": len(nets),
                "initial_sha": hashlib.sha256(a.initial.read_bytes()).hexdigest(),
            },
        )
    print("trained", a.programs, step, list(nets), round(seconds, 2), flush=True)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--programs", type=int, required=True)
    p.add_argument("--updates", type=int, required=True)
    p.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    p.add_argument("--seeds", type=int, nargs="+", default=[9633, 5003])
    torch.set_num_threads(1)
    train(p.parse_args())
