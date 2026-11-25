"""Replay one already-woken root in the frozen decoder, for hardware profiling."""

import argparse
import json
from collections import Counter
from pathlib import Path
from time import time_ns
from types import SimpleNamespace

import numpy as np
import torch

from cost_bake import LearnedCostEntries
from cost_boundary_growth import ROLE, RULE, SOURCE, WATERMARK, restore
from entry_model import Family
from entry_wiring import use_wiring
from event_addresses import Directory
from recursive_ripsat_study import setup_policy
from recursive_rollout import get_policy


@torch.no_grad()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("arm", choices=("base", "frozen"))
    args = p.parse_args()
    torch.set_num_threads(1)
    state = torch.load(args.store / "structure-rl.pt", weights_only=True)
    folder, _, generator, owner = setup_policy(
        args.data, args.store, "sum-divisors", state, True, policy_cls=LearnedCostEntries
    )
    policy = get_policy(args.data, folder, "free", "multi")
    rd = policy.reader
    restore(rd, args.store / "sum-divisors-native-memory.jsonl")
    owner.family = Family(rd, owner.program, owner.manifest)
    use_wiring(owner.family, owner.graph)
    owner.count = Counter()
    txn = owner.txn = SimpleNamespace(run=541)
    stats = Counter()
    mem = generator.memory = Directory(rd, stats)
    ix = np.asarray([mem.bank(mem.roles[RULE][ROLE]).positions[SOURCE]])
    generator.tree = SimpleNamespace(emit=lambda *args: ())
    generator.wake = lambda *args: [(RULE, ROLE, ix, True)]
    # Isolate the pointer decoder and the exact chooser. No other event or takeover can run.
    generator.higher = SimpleNamespace(start=lambda *args: None, choose=lambda *args: None)
    if args.arm == "frozen":
        generator.higher.cost_bake = owner.cost_bake
    frame = {"rules": [(RULE, WATERMARK)], "run": 541}
    rounds = 5 if args.arm == "base" else 30000

    def one():
        generator.run_snapshot(frame, None, rd, policy.model, txn, stats, float("inf"))

    one()
    per = stats["parent_candidate_scores"]
    if per != (404643 if args.arm == "base" else 0) or stats["generated_proofs"]:
        raise ValueError(dict(stats))
    start = time_ns()
    for _ in range(rounds):
        one()
    end = time_ns()
    if stats["parent_candidate_scores"] != (rounds + 1) * per or stats["generated_proofs"]:
        raise ValueError("unstable frozen event")
    out = args.store / f"boundary/event-{args.arm}.json"
    out.write_text(
        json.dumps(
            dict(
                begin_unix_ns=start, end_unix_ns=end, rounds=rounds, scores_per_root=per, generated_proofs=0
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
