"""Attribute fixed-policy reference proof losses and isolate the pending-pool cap."""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import torch

from anchor_set_audit import check
from recursive_agent import BEAM, FANOUT, RUN_PACKETS
from recursive_rollout import EVAL, get_policy
from recursive_train import binary, folder, keys, read


def audit(root, case):
    d = folder(root, case)
    tape = read(d / "tape.json")
    by = defaultdict(list)
    for q in tape["requests"]:
        by[q["run"]].append(q)
    records = {}
    for arm in ("free", "pending", "roomy"):
        pol = get_policy(root, d, "free" if arm == "free" else "pending", "dagger")
        if arm == "roomy":
            pol.pool_limit = math.inf
        packets = []
        with (d / "memory.jsonl").open() as f:
            for frame in map(json.loads, f):
                run = frame["run"]
                teacher = by[run]
                wanted = defaultdict(lambda: defaultdict(list))
                states = {}
                lengths = {}
                for q in teacher:
                    r = q["rule"]
                    path = tuple(keys(q)[j] for j in pol.reader.order(r))
                    t = q["token"]
                    states[t] = (-1, "rule_budget")
                    lengths[t] = len(path)
                    for j, k in enumerate(path):
                        wanted[r, path[:j]][k].append(t)

                def mark(r, seq, dom, stage):
                    children = wanted.get((r, seq), {})
                    if stage == "domain":
                        for ids in children.values():
                            for t in ids:
                                states[t] = max(
                                    states[t],
                                    (
                                        4 * len(seq),
                                        "root_unvisited"
                                        if not seq
                                        else "partner_not_retrieved",
                                    ),
                                )
                    tags = {
                        "domain": (1, "fanout"),
                        "fanout": (2, "beam"),
                        "beam": (3, "branch_budget"),
                    }
                    level, reason = tags[stage]
                    for k in dom:
                        for t in children.get(k, ()):
                            states[t] = max(states[t], (4 * len(seq) + level, reason))

                pol.observer = lambda r, seq, dom: mark(r, seq, dom, "domain")
                pol.selection_observer = mark
                spent_before = pol.count["expansions"]
                rows = pol.issue(frame)
                for q in rows:
                    q["token"] = len(packets) + 1
                    packets.append(q)
                issued = {(q["rule"], keys(q)) for q in rows}
                stages = Counter(
                    "issued"
                    if (q["rule"], keys(q)) in issued
                    else states[q["token"]][1]
                    for q in teacher
                )
                bound = 0
                for rid, wm in frame["rules"]:
                    roles = pol.reader.order(rid)
                    if not roles:
                        bound += int(
                            not wm
                            or not pol.reader.iface.rules[rid]["metadata"]["seminaive"]
                        )
                        continue
                    sizes = [
                        len(pol.reader.live[pol.next_table(rid, j)])
                        for j in range(len(roles))
                    ]
                    bound += min(math.prod(sizes), FANOUT if len(roles) == 1 else BEAM)
                rec = records.setdefault(
                    run,
                    dict(
                        case=case,
                        run=run,
                        teacher=len(teacher),
                        packet_cap=RUN_PACKETS,
                        free_structural_upper=min(bound, RUN_PACKETS),
                    ),
                )
                rec[arm + "_issued"] = len(rows)
                if arm == "free":
                    rec["expansions"] = pol.count["expansions"] - spent_before
                    rec["packet_cap_reached"] = int(len(rows) == RUN_PACKETS)
                    rec["overflow_packet_lower_bound"] = max(
                        0, len(teacher) - RUN_PACKETS
                    )
                    rec["overflow_all_caps_lower_bound"] = max(
                        0, len(teacher) - rec["free_structural_upper"]
                    )
                    terminal = Counter()
                    for q in teacher:
                        t = q["token"]
                        depth, reason = states[t]
                        if (q["rule"], keys(q)) not in issued and reason in (
                            "beam",
                            "fanout",
                        ):
                            terminal[reason] += int(depth // 4 + 1 == lengths[t])
                    rec["terminal_fanout"] = terminal["fanout"]
                    rec["terminal_beam"] = terminal["beam"]
                    for key in (
                        "rule_budget",
                        "root_unvisited",
                        "partner_not_retrieved",
                        "fanout",
                        "beam",
                        "branch_budget",
                        "issued",
                    ):
                        rec[key] = stages[key]
        rep = check(d, binary(root), tape, packets)
        found = defaultdict(set)
        for run, _, target, _ in rep["recall_verdicts"]:
            if target is not None:
                found[run].add(target)
        for run, rec in records.items():
            rec[arm + "_hits"] = found[run]
    for rec in records.values():
        capped, roomy = rec["pending_hits"], rec["roomy_hits"]
        rec["pool_cap_only_lost"] = len(roomy - capped)
        rec["pool_cap_only_gained"] = len(capped - roomy)
        for a in ("free", "pending", "roomy"):
            rec[a + "_hits"] = len(rec[a + "_hits"])
    return records.values()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    with a.out.open("w") as stream:
        w = None
        for c in EVAL:
            rows = list(audit(a.root.resolve(), c))
            if w is None:
                w = csv.DictWriter(
                    stream, fieldnames=list(rows[0]), lineterminator="\n"
                )
                w.writeheader()
            w.writerows(rows)
            stream.flush()
            print(c, len(rows), flush=True)
