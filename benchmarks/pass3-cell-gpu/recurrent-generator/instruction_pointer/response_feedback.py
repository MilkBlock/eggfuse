"""Matched-RNG held response intervention with the publication, schedule and draft fixed."""

import json
from collections import Counter

import numpy as np
import torch

from discrete_cells import from_q
from discrete_draft import plan
from discrete_editor import sampler
from discrete_study import views
from recursive_train import folder
from response_study import arguments, memory, weights
from scaling_bake import save


@torch.no_grad()
def study(a):
    rows = []
    for name in ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119"):
        d = folder(a.data, name)
        forks = {
            v["run"]: v
            for v in map(
                json.loads, (a.forks / (name + ".jsonl")).read_text().splitlines()
            )
        }
        m = memory(a, d)
        models = {arm: weights(a, arm) for arm in ("C", "D", "E")}
        with (d / "memory.jsonl").open() as source:
            for f in map(json.loads, source):
                m.update(f)
                row = forks.pop(f["run"], None)
                if row is None:
                    continue
                kinds = {k for k, _, _ in views(row)}
                if {"empty", "duplicate"} <= kinds and row["cases"]["bad"]["counts"][
                    "rejected"
                ].get("version", 0):
                    good, bad = (from_q(row[k]) for k in ("a", "bad"))
                    for arm, (marks, nets) in models.items():
                        method = "editor" if arm == "C" else "flow"
                        answers = []
                        for cell, ok in ((good, True), (bad, False)):
                            m.reply([(cell, ok)])
                            seqs = [
                                tuple(
                                    v.cell
                                    for v in sampler(
                                        nets[method],
                                        marks,
                                        m,
                                        plan([good]),
                                        method,
                                        1 if arm == "C" else 4,
                                        np.random.default_rng(s),
                                        Counter(),
                                    )
                                )
                                for s in range(8)
                            ]
                            answers.append(seqs)
                        rows.append(
                            dict(
                                case=name,
                                run=f["run"],
                                arm=arm,
                                n=8,
                                accepted_clear=sum(not x for x in answers[0]),
                                rejected_preserve=sum(x == (good,) for x in answers[1]),
                                correct_both=sum(
                                    not x and y == (good,) for x, y in zip(*answers)
                                ),
                                wrong_delete=sum(good not in x for x in answers[1]),
                                changed=sum(x != y for x, y in zip(*answers)),
                            )
                        )
                if not forks:
                    break
    save(a.out / "feedback.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    study(arguments())
