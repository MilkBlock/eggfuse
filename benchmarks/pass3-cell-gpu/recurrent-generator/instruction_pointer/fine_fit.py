"""Train A–E on the same pages, precomputed candidate paths and optimizer schedule."""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from torch.nn import functional as F

from address_scores import weight
from cell_transaction import STATUS
from coverage_onpolicy import IncompleteBudget, coverage_gradient
from credit_scale_fit import load_shard
from credit_scale_programs import split_check
from discovery_score import token
from discovery_states import cli
from fine_credit import labels
from query_fit import log_paths
from transition_credit import contrasts, reduce_data, schema
from transition_fit import prepare

ARMS = ("A", "B", "C", "D", "E")


def scope_loss(factors, index, record, budget, arm):
    """Drop unknown targets. Conditional binding loss has no template-logit gradient."""
    p = factors.prod(1)
    zero = p.sum() * 0
    groups = defaultdict(list)
    for c, i in index.items():
        if c in record["self_positive"] or (arm == "E" and c in record["positive"]):
            groups[record["positive"][c]].append(i)
    discovery = zero
    for ids in groups.values():
        mass = p[ids].sum().clamp(max=1 - 1e-6)
        discovery = discovery + torch.expm1(budget * torch.log1p(-mass)) / budget
    if arm == "A":
        return discovery + sum(
            (p[i] for c, i in index.items() if c in record["negative"]), zero
        )
    rules = set()
    loss = discovery
    for c, i in index.items():
        if c in record["inactive"] and (c.rule, c.higher) not in rules:
            rules.add((c.rule, c.higher))
            loss = loss + factors[i, 0]
        elif c in record["bad_binding"]:
            loss = loss + factors[i, 0].detach() * factors[i, 1:].prod()
    # Guard failure and watermark carry labels, but the actor has no guard or
    # issuance decision. Do not manufacture a bad-parent or bad-template target.
    return loss


def load_data(a, idx, bank):
    files = sorted((a.out / "buffer").glob(f"{idx:04}-*.gz"))
    shards = {}
    sides = {}
    for path in files:
        sh = load_shard(path)
        shards[sh["branch"]] = sh
        side = load_shard(a.out / "credit" / path.name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != side["source_sha256"]:
            raise ValueError("credit hash does not match raw experience")
        sides[sh["branch"]] = side
    ir = json.loads((bank / "program.json").read_bytes())
    rec = reduce_data(shards, schema(ir), {b: (10**9, 10**9) for b in shards}, idx)
    edits = []
    edges = []
    for b, sh in shards.items():
        side = sides[b]
        ids = {}
        for j, (event, ctx) in enumerate(
            zip(sh["events"], side["events"], strict=True)
        ):
            row = rec[b, j]
            row["inactive"] = set()
            row["bad_binding"] = set()
            dirty = {r: bool(d) for r, w, d in ctx["rules"]}
            for raw, result in zip(event["generated"], ctx["rows"], strict=True):
                c = token(raw)
                uid, status, g, present, issued_dirty = result
                feedback = labels(
                    STATUS[status], dirty[c.rule], issued_dirty, g, present
                )
                if (
                    feedback.get("timing", (None,))[0] == "template_at_generation"
                    and issued_dirty is False
                ):
                    row["inactive"].add(c)
                if STATUS[status] == "binding":
                    row["bad_binding"].add(c)
                ids[uid] = (b, j), c
        run_index = {e["frame"]["run"]: j for j, e in enumerate(sh["events"])}
        for r, bad, good, slot, _ in side["edits"]:
            edits.append(((b, run_index[r]), token(bad), token(good), slot))
        for _, parent, _, child, _ in side["edges"]:
            # Teacher-assisted endpoints have no autonomous generation decision.
            if parent in ids and child in ids:
                edges.append((ids[parent], ids[child]))
    return shards, rec, contrasts(rec), edits, edges


def path_factors(net, entry):
    packet, index, _, _ = entry
    return log_paths(net, packet, np.arange(len(index)), "mps")


def update(
    net,
    opt,
    sampler,
    arm,
    record_at_state,
    batches,
    k,
    pare,
    edit,
    edge,
    budget,
    gate,
    objective,
    slot_limit,
    update_count,
):
    cache = {}

    def factors(key):
        if key not in cache:
            cache[key] = path_factors(net, batches[key])
        return cache[key]

    def logs(key, c):
        return factors(key)[batches[key][1][c]].clamp_min(1e-30).log()

    opt.zero_grad()
    row = batches[k]
    loss = (
        scope_loss(factors(k), row[1], record_at_state, int(budget), arm)
        if row and objective == "slot"
        else next(net.parameters()).sum() * 0
    )
    if objective == "complete" and row:
        record = record_at_state
        credit = {
            c: s
            for c, s in record["positive"].items()
            if c in record["self_positive"] or arm == "E"
        }

        def marginal(items):
            counts = Counter(credit[c] for c in items if c in credit)
            return [
                int(c in credit and counts[credit[c]] == 1)
                - int(arm == "A" and c in record["negative"])
                for c in items
            ]

        inactive = {c.rule for c in record["inactive"]}
        local = (
            None
            if arm == "A"
            else (
                lambda c: -int(c.rule in inactive),
                lambda c: -int(c in record["bad_binding"]),
            )
        )
        try:
            loss, _, slots, used = coverage_gradient(
                net,
                row[3],
                credit,
                gate,
                int(budget),
                sampler,
                marginal=marginal,
                local=local,
                max_slots=slot_limit,
            )
        except IncompleteBudget as error:
            update_count[arm + "_censored_steps"] += 1
            update_count[arm + "_censored_slots"] += error.slots
            update_count[arm + "_censored_complete"] += error.delivered
            update_count[arm + "_censored_goal"] += error.goal
            return
        update_count[arm + "_optimizer_slots"] += slots
        update_count[arm + "_optimizer_complete"] += used
    if arm in "CDE" and pare:
        x, y, c = pare
        loss = loss + 0.05 * F.softplus(logs(y, c).sum() - logs(x, c).sum())
        update_count[arm + "_pairs"] += 1
    if arm in "DE" and edit:
        k2, bad, good, slot = edit
        # Same conditioning prefix; target only the changed parent.
        loss = loss + 0.05 * F.softplus(
            logs(k2, bad)[1 + slot] - logs(k2, good)[1 + slot]
        )
        update_count[arm + "_local"] += 1
    if arm == "E" and edge:
        (x, c), (y, d) = edge
        # Both goals retain their positive sign. Split a single
        # additional path imitation budget over the observed edge.
        loss = loss - 0.025 * (logs(x, c).sum() + logs(y, d).sum())
        update_count["E_edges"] += 1
    loss.backward()
    torch.nn.utils.clip_grad_norm_(net.parameters(), 5, error_if_nonfinite=True)
    opt.step()
    update_count[arm + "_steps"] += 1


def fit(a):
    if not 0 < a.programs <= 256:
        raise ValueError("programs from 256 onwards are reserved for evaluation")
    signatures = split_check(a.previous, [*range(a.programs), *range(256, 264)])
    if len(set(signatures.values())) != len(signatures):
        raise ValueError("evaluation shares a normalized program graph")
    start = perf_counter()
    seeds = (9633, 5003)
    cfg = {}
    for seed in seeds:
        for arm in a.arms:
            net = weight(a).to("mps")
            net.load_state_dict(torch.load(a.initial, weights_only=True))
            cfg[seed, arm] = net, torch.optim.AdamW(net.parameters(), lr=0.00015)
    samplers = {key: np.random.default_rng(key[0] + 19) for key in cfg}
    gate = weight(a).to("mps").eval()
    update_count = Counter()
    for pos, idx in enumerate(np.random.default_rng(609).permutation(a.programs)):
        idx = int(idx)
        bank = a.previous / "programs" / f"{idx:04}"
        data, rec, pairs, edits, edges = load_data(a, idx, bank)
        for seed in seeds:
            rng = np.random.default_rng(seed + idx * 171)
            repeat = a.steps // a.programs + (pos < a.steps % a.programs)
            keys = sorted(rec)
            chosen = [keys[i] for i in rng.integers(len(keys), size=repeat)]
            pc, lc, dc = [
                [options[i] for i in rng.integers(len(options), size=repeat)]
                if options
                else [None] * repeat
                for options in (pairs, edits, edges)
            ]
            forced = [p for p in pc if p]
            for item in lc:
                if item:
                    k, c, d, _j = item
                    forced.extend([(k, k, c), (k, k, d)])
            for edge in dc:
                if edge:
                    for k, c in edge:
                        forced.append((k, k, c))
            batches = prepare(
                a, bank, data, rec, chosen, forced, rng, gate, a.objective == "complete"
            )
            for k, pare, edit, edge, budget in zip(
                chosen,
                pc,
                lc,
                dc,
                rng.choice([4, 16, 64, 256], size=repeat),
                strict=True,
            ):
                for arm in a.arms:
                    net, opt = cfg[seed, arm]
                    update(
                        net,
                        opt,
                        samplers[seed, arm],
                        arm,
                        rec[k],
                        batches,
                        k,
                        pare,
                        edit,
                        edge,
                        budget,
                        gate,
                        a.objective,
                        a.slot_limit,
                        update_count,
                    )
        if (pos + 1) % 8 == 0:
            print("trained", pos + 1, flush=True)
    torch.mps.synchronize()
    for (seed, arm), (net, _) in cfg.items():
        dest = a.out / "weights" / str(seed)
        dest.mkdir(parents=True, exist_ok=True)
        torch.save(net.cpu().state_dict(), dest / f"{a.tag}-{arm}.pt")
    (a.out / f"fit-{a.tag}.json").write_text(
        json.dumps(
            {
                "counts": update_count,
                "steps": a.steps,
                "programs": a.programs,
                "seeds": seeds,
                "seconds": perf_counter() - start,
                "initial": str(a.initial),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = cli()
    p.add_argument("--programs", type=int, default=80)
    p.add_argument("--steps", type=int, default=400)
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--arms", nargs="+", choices=ARMS, default=ARMS)
    p.add_argument("--tag", default="fine")
    p.add_argument("--objective", choices=["complete", "slot"], default="slot")
    p.add_argument("--slot-limit", type=int, default=8192)
    torch.set_num_threads(1)
    fit(p.parse_args())
