"""Offline budget bounds on native witnessed sets before fitting either generator."""

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from continuation_audit import arguments
from discrete_cells import from_q
from draft_multitarget import snapshots
from metal_scaling import CASES, models
from recursive_train import folder, read


def bounds(cells, n=4):
    grouped = defaultdict(Counter)
    for c in set(cells):
        grouped[c.rule][c.refs[:1]] += 1
    counts = sorted((sum(v.values()) for v in grouped.values()), reverse=True)
    rule = sum(counts[:n])
    first = sum(sum(sorted(v.values(), reverse=True)[:n]) for v in grouped.values())
    later = sum(min(n, k) for v in grouped.values() for k in v.values())
    widths = [
        sum(sorted((min(k, n) for k in v.values()), reverse=True)[:n])
        for v in grouped.values()
    ]
    return {
        "rules": len(grouped),
        "bindings": sum(counts),
        "rule4": rule,
        "four_rules_four_complete": sum(min(n, k) for k in counts[:n]),
        "first4": first,
        "later4": later,
        "cascade4": sum(sorted(widths, reverse=True)[:n]),
    }


def args():
    p = arguments()
    p.add_argument("--corpus", type=Path, required=True)
    return p


@torch.no_grad()
def run(a):
    a.out.mkdir(parents=True, exist_ok=True)
    marks, _ = models("1M")
    marks.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[0]
    )
    records = []
    attempts = []
    for case in CASES:
        d = folder(a.data, case)
        groups = defaultdict(set)
        for q in read(d / "tape.json")["requests"]:
            groups[q["run"]].add(from_q(q))
        with (d / "memory.jsonl").open() as f:
            for line in f:
                run = json.loads(line)["run"]
                records.append(dict(case=case, run=run, **bounds(groups[run])))
        if a.bounds_only:
            continue
        for m, r, gold in snapshots(a, case, "teacher"):
            rng = np.random.default_rng(536 + r)
            rules = {c.rule for c in gold}
            roots = {(c.rule, c.refs[:1]) for c in gold}
            for budget in (4, 16, 64, 256):
                counts = Counter()
                seen = set()

                def record(key, counts=counts, rules=rules):
                    counts["wrong_template"] += key[1] or key[0] not in rules

                m.on_template_draw = record
                for j in range(budget):
                    c = marks.draw(m, rng, Counter())
                    if c is None:
                        counts["incomplete"] += 1
                    else:
                        counts["repeat"] += c in seen
                        counts["root_outside_witnesses"] += (
                            c.rule,
                            c.refs[:1],
                        ) not in roots
                        seen.add(c)
                attempts.append(
                    dict(
                        case=case,
                        run=r,
                        budget=budget,
                        hits=len(seen & gold.keys()),
                        oracle=min(budget, len(gold)),
                        **counts,
                    )
                )
    for name, rows in [("budget", records), ("audit-draws", attempts)]:
        if a.bounds_only and name == "audit-draws":
            continue
        (a.out / (name + ".json")).write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    parser = args()
    parser.add_argument("--bounds-only", action="store_true")
    run(parser.parse_args())
