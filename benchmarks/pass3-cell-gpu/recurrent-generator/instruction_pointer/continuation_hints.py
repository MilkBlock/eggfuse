"""Offline prompted retrieval of distinct credited operations on identical native frozen states."""

import json
import subprocess
from collections import Counter, defaultdict

import numpy as np
import torch

from continuation_audit import arguments
from discrete_cells import from_q
from discrete_editor import sampler
from metal_scaling import CASES, models
from recursive_train import binary, folder, read
from response_plan import split_draft
from response_study import memory

BUDGETS = (1, 4, 16, 32)
PROMPTS = ("free", "count", "rule", "prefix", "count_rule", "count_prefix")


def probe(m, marks, rate, method, prompt, target, rng, initial=()):
    gold = {cell: gain for cell, gain in target}
    order = [c for c, _ in target]
    seen = set()
    draft = initial
    results = []
    st = Counter()
    orig = marks.draw

    def draw(*args, **kw):
        n = st["attempts"]
        st["attempts"] += 1
        goal = order[n % len(order)]
        if "rule" in prompt or "prefix" in prompt:
            kw["oracle_key"] = (goal.rule, goal.higher)
        if "prefix" in prompt:
            kw["diagnostic_refs"] = goal.refs[:1]
            st["given_parents"] += len(goal.refs[:1])
        return orig(*args, **kw)

    marks.draw = draw
    try:
        # Count-oracle permits one direct mark per remaining distinct credited
        # request. It bypasses all subsequent length and dispatch decisions.
        # Autonomous modes retain the actual one-head-per-page contract.
        for b in range(1, max(BUDGETS) + 1):
            if "count" in prompt:
                issued = [draw(m, rng, st)] if b <= len(order) else []
            else:
                draft = sampler(
                    rate, marks, m, draft, method, 4 if method == "flow" else 1, rng, st
                )
                head, draft = split_draft(draft, {r for r, _ in m.ids})
                issued = [x.cell for x in head]
            for c in issued:
                if c is not None:
                    st["issued"] += 1
                    if c in gold:
                        seen.add(c)
            if b in BUDGETS:
                results.append(
                    {
                        "page": b,
                        "hits": len(seen),
                        "ops": sum(gold[c] for c in seen),
                        "stats": dict(st),
                    }
                )
    finally:
        del marks.draw
    return results


@torch.no_grad()
def run(a):
    out = a.out / "hints"
    out.mkdir(exist_ok=True)
    for case in a.cases:
        d = folder(a.data, case)
        tape = d / "tape.json"
        frames = list(map(json.loads, (d / "memory.jsonl").open()))
        rep = json.loads(
            subprocess.check_output(
                [
                    binary(a.data),
                    "replay",
                    d / "program.json",
                    tape,
                    "time",
                    "--ept-origins",
                ]
            )
        )
        assert rep["state_sha"] == read(d / "capture.json")["state_sha"]
        raw = read(tape)["requests"]
        gains = dict(rep["ept"]["origins"])
        groups = defaultdict(list)
        for q in raw:
            groups[q["run"]].append(q)
        bins = defaultdict(list)
        for r, group in groups.items():
            n = sum(gains.get(q["token"], 0) > 0 for q in group)
            if n:
                bins[min(3, int(np.log2(n)) // 2)].append(r)
        rng = np.random.default_rng(2894)
        take = {
            int(r)
            for arr in bins.values()
            for r in rng.choice(arr, min(3, len(arr)), replace=False)
        }
        nets = {}
        for seed in a.seeds:
            for mode in a.arms:
                path = (
                    a.previous / f"s{seed}/1M-n1000000"
                    if mode == "prior"
                    else a.out / f"s{seed}" / mode
                ) / "weights.pt"
                pair = models("1M")
                for model, state in zip(pair, torch.load(path, weights_only=True)):
                    model.load_state_dict(state)
                nets[seed, mode] = pair
        m = memory(a, d)
        rows = []
        for f in frames:
            m.update(f)
            if f["run"] not in take:
                continue
            group = groups[f["run"]]
            positive = [i for i, q in enumerate(group) if gains.get(q["token"], 0) > 0]
            n = len(positive)
            remaining = int(rng.integers(1, min(24, n) + 1))
            j = positive[n - remaining]
            target = [
                (from_q(q), gains[q["token"]])
                for q in group[j:]
                if gains.get(q["token"], 0) > 0
            ]
            if j:
                m.reply([(from_q(group[j - 1]), True)])
            assert len(dict(target)) == len(target)
            for (seed, arm), (marks, rate) in nets.items():
                for prompt in PROMPTS:
                    vals = probe(
                        m,
                        marks,
                        rate,
                        "editor" if arm.startswith("editor") else "flow",
                        prompt,
                        target,
                        np.random.default_rng(seed + f["run"]),
                    )
                    rows.append(
                        {
                            "case": case,
                            "run": f["run"],
                            "prefix": j,
                            "targets": len(target),
                            "ops": sum(x[1] for x in target),
                            "arities": dict(Counter(len(c.refs) for c, _ in target)),
                            "arm": arm,
                            "seed": seed,
                            "prompt": prompt,
                            "curve": vals,
                        }
                    )
        (out / f"{case}{a.suffix}.json").write_text(json.dumps(rows) + "\n")
        print(case, len(take), len(rows), flush=True)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--arms", nargs="+", default=["prior", "editor", "flow"])
    p.add_argument("--suffix", default="")
    p.add_argument("--seeds", nargs="+", type=int, default=[243, 536, 8201])
    p.add_argument("--cases", nargs="+", default=CASES)
    torch.set_num_threads(1)
    run(p.parse_args())
