"""On-policy parameter-space RL over complete native multi-event episodes."""
import argparse
from collections import Counter
import numpy as np
import json
import hashlib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter
import torch

from event_generator import EventGenerator
from projected_entries import ProjectedEntries
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_ripsat import OpenEntries
from recursive_train import binary, folder, read
from transaction_native import execute


def setup_policy(data, store, case, state, opened, exploration_seed=None, policy_cls=None):
    d = folder(data, case)
    p = EventGenerator(data, case, Path("run-recall/cell-events"), "B")
    program = read(d / "program.json")
    graph = torch.load(store / "graph.pt", weights_only=True)
    contract = json.loads(subprocess.check_output([binary(data), "receipt-contract", d / "program.json"]))
    if contract["recipe_sha256"] != program["recipe"]["sha256"]:
        raise ValueError("native contract belongs to another Recipe")
    cls = policy_cls or (OpenEntries if opened else ProjectedEntries)
    policy = cls(program, store, store / "wired.pt", graph, read(store / "entry-contracts.json"), contract["rules"])
    if opened and exploration_seed is not None:
        policy.exploration = np.random.default_rng(exploration_seed)
    p.higher = policy
    policy.model.load_state_dict(state)
    return d, program, p, policy


def episode(data, store, case, label, state, opened, limit=None, exploration_seed=None, policy_cls=None, boundary_audit=False):
    start = perf_counter()
    d, program, p, policy = setup_policy(data, store, case, state, opened, exploration_seed, policy_cls)
    setup_seconds = perf_counter() - start
    # Keep bounded disk usage: native scratch is private to each invocation.
    with TemporaryDirectory(dir=store) as tmp:
        result = execute(data, case, study=p, seconds=900, series=tmp, limit=limit)
        result["setup_seconds"] = setup_seconds
        suffix = f"-first{limit}" if limit else ""
        work = Path(tmp) / (case + "-stream-multi" + suffix)
        align = work / "align.json"
        target = Target(program, snapshot(data, d, "reference", "-", limit, align)[0])
        initial = target.match(snapshot(data, d, "reference", "-", 0, align)[0])
        if opened:
            report = json.loads(subprocess.check_output([binary(data), "replay", d / "program.json",
                work / "issued.json", "audit", str(result["runs"]), "--ept-origins"]))
            if report["state_sha"] != result["state_sha"]:
                raise ValueError("origin attribution changed the independent endpoint")
            if boundary_audit:
                # Per-Run checks cover transient publications and repairs as well as the endpoint.
                checks = {k: hashlib.sha256(json.dumps(report[k], separators=(",", ":")).encode()).hexdigest()
                          for k in ("schedule", "rhs", "resumes", "writes", "events")}
                checks["effective_ledger"] = report["ept"]["ledger_sha256"]
                result["boundary_hashes"] = checks
            credit = Counter()
            for tok, n in report["ept"]["origins"]:
                if tok in policy.suffix_tokens:
                    credit[policy.suffix_tokens[tok][0]] += n
            result["new_suffix_operations"] = dict(credit)
            if hasattr(policy, "structure_report"):
                result["structures"] = policy.structure_report(report["ept"]["origins"])
        if hasattr(policy, "audit_partners"):
            result["partner_audit"] = policy.audit_partners(data, case, work, result)
        result["reference"] = len(target.gold) - len(initial)
        result["facts"] = len(target.match(read(work / "state.json")) - initial)
    if result["termination"] != "schedule_end":
        raise RuntimeError(result["termination"])
    result.pop("trace")
    work = result["work"]
    result["open_actions"] = dict(policy.action_counts) if opened else {}
    result["open_decision_runs"] = len(policy.action_runs) if opened else 0
    result["published_recursive"] = [x for x in policy.lineage if x[1] > 1] if opened else []
    # One terminal choice per event, one charged extra choice on the sparse
    # page, one operand instruction when it actually runs. Keep CCP counts separate.
    result["terminal_decisions"] = work["primitive_terminal_choices"] + work["entry_terminal_choices"] if "primitive_terminal_choices" in work else 0
    # Control tokens and emitted proof requests are both charged; score visits
    # are reported separately from issued tokens.
    result["charged_with_decisions"] = result["paid"] + result["terminal_decisions"] + sum(result["open_actions"].values()) + work.get("open_contract_choices", 0)
    dump(store / f"{case}-{label}.json", result)
    print(case, label, result["facts"], result["signed_ops"], result["paid"],
          round(result["wall"], 2), result["open_actions"], flush=True)
    return result


def reward(x, base):
    # A full-episode return, with all effectiveness credit from the native
    # settled-operation ledger. An otherwise cheap incomplete episode always loses.
    if x["facts"] < base["facts"]:
        return -2.0 - (base["facts"] - x["facts"]) / max(1, base["facts"])
    def change(k):
        return (x[k] - base[k]) / max(1, base[k])
    value = change("signed_ops") - .5 * change("charged_with_decisions") - .5 * change("wall")
    return max(-1., min(1., value))


def train(a, policy_cls=None, initial="wired.pt", checkpoint="recursive-rl.pt"):
    state = torch.load(a.store / initial, weights_only=True)
    base = episode(a.data, a.store, a.case, "train-origin", state, False, a.limit)
    gen = torch.Generator().manual_seed(a.seed)
    log = []
    for i in range(a.steps):
        # Mirrored exploration in the last existing layers of B. Each sampled
        # policy makes its own decisions for the whole episode, including wakes.
        noise = {k: torch.randn(v.shape, generator=gen) if k.startswith(("2.", "4.")) else torch.zeros_like(v)
                 for k, v in state.items()}
        ret = {}
        for sign in ((1, -1) if i % 2 == 0 else (-1, 1)):
            draw = {k: v + sign * a.sigma * noise[k] for k, v in state.items()}
            x = episode(a.data, a.store, a.case, f"train-{i}-{sign}", draw, True, a.limit, a.seed + i, policy_cls)
            ret[sign] = reward(x, base)
        advantage = ret[1] - ret[-1]
        for k in state:
            state[k] = state[k] + .02 * max(-1., min(1., advantage / (2*a.sigma))) * noise[k]
        log.append(dict(step=i, positive=ret[1], negative=ret[-1], advantage=advantage))
    torch.save(state, a.store / checkpoint)
    dump(a.store / "training.json", dict(seed=a.seed, sigma=a.sigma, limit=a.limit, episodes=log))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+", choices=["train", "original", "open", "rl"])
    p.add_argument("--limit", type=int)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--sigma", type=float, default=.06)
    p.add_argument("--seed", type=int, default=431)
    p.add_argument("--rep", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        if arm == "train":
            train(a)
        else:
            weights = a.store / ("recursive-rl.pt" if arm == "rl" else "wired.pt")
            episode(a.data, a.store, a.case, f"{arm}-{a.rep}", torch.load(weights, weights_only=True),
                    arm != "original", a.limit)
