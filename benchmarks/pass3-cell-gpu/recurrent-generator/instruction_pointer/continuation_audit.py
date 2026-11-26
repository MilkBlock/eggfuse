"""Reproduce the archived sampler without changing its RNG, and attribute every page."""

import argparse
import json
from collections import Counter
from pathlib import Path

import torch

from discrete_draft import Local
from metal_scaling import models
from recursive_train import folder, read
from response_plan import ResponsePolicy
from response_study import memory
from transaction_native import execute


class Audit(ResponsePolicy):
    def dispatch_prefix(self, items, stats):
        head = items[0].cell if items else None
        reason = (
            "empty"
            if head is None
            else "unscheduled"
            if head.rule not in self.scheduled
            else "unpublished"
            if any(isinstance(x, Local) or x[2] < 0 for x in head.refs)
            else "issued"
        )
        self.page.update(
            reason=reason, length=len(items), head=head.rule if head else None
        )
        self.pages.append(self.page)
        self.page = self.newpage()
        return super().dispatch_prefix(items, stats)

    def newpage(self):
        return {
            "run": self.run_id,
            "attempts": [],
            "insert_hazard": 0.0,
            "edit_calls": 0,
            "delete_hazard": 0.0,
        }

    def run_snapshot(self, frame, *args):
        self.run_id = frame["run"]
        self.page = self.newpage()
        if getattr(self, "ablate_head", False) and self.run_id == 2:
            # Offline intervention on the known failed draft. No rule/parent is supplied.
            self.held_aside = self.draft[:1]
            self.draft = self.draft[1:]
        super().run_snapshot(frame, *args)

    def issue(self, items, txn, stats):
        rows = super().issue(items, txn, stats)
        for item in items:
            self.pages[-1].setdefault("receipts", []).append(
                [item.cell.rule, rows[item.uid].tolist()]
            )
        return rows


def monitor(pol, m, marks, rates):
    def note(_module, inputs, output):
        x = inputs[0]
        k = 4 - round(4 * x[0, -6].item())
        rate = torch.nn.functional.softplus(output) / k
        pol.page["insert_hazard"] += float(rate[:, 0].sum())
        pol.page["delete_hazard"] += float((rate[:, 1] * x[:, -5]).sum())
        pol.page["edit_calls"] += 1

    rates.register_forward_hook(note)
    draw = marks.draw

    def recorded(*args, **kw):
        selected = []
        m.on_template_draw = selected.append
        token = draw(*args, **kw)
        pol.page["attempts"].append([selected, token is not None])
        return token

    marks.draw = recorded


def run(a):
    d = folder(a.data, "sum-divisors")
    dest = (a.out / "audit").resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for seed, waves, aside in [
        (243, 2, False),
        (536, 2, False),
        (8201, 2, False),
        (243, 8, False),
        (243, 2, True),
    ]:
        marks, rates = models("1M")
        weights = a.previous / f"s{seed}/1M-n1000000/weights.pt"
        for net, sd in zip((marks, rates), torch.load(weights, weights_only=True)):
            net.load_state_dict(sd)
        m = memory(a, d)
        pol = Audit(m, marks, {"flow": rates}, "empty", 4, 536, waves)
        pol.ablate_head = aside
        pol.pages = []

        monitor(pol, m, marks, rates)
        tag = f"s{seed}-w{waves}" + ("-set-aside" if aside else "")
        row = execute(
            a.data, "sum-divisors", study=pol, seconds=180, series=str(dest / tag)
        )
        if waves == 2 and not aside:
            prior = read(weights.parent / "cpu-sum-divisors-cpu-b0.json")
            for key in ["paid", "verdicts", "state_sha", "signed_ops"]:
                assert row[key] == prior[key], (tag, key)
        (dest / f"{tag}.json").write_text(
            json.dumps({"pages": pol.pages, "run": row}) + "\n"
        )
        print(tag, Counter(p["reason"] for p in pol.pages), row["verdicts"], flush=True)


def arguments():
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(arguments().parse_args())
