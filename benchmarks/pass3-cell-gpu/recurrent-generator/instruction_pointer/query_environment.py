"""Native pre-issue telemetry and fixed-width conditioning of the existing address MLP."""

import json
from collections import Counter

import torch

from address_runtime import AddressPage, code
from metal_scaling import models
from response_plan import ResponseMemory
from response_study import memory


def stamp(watermark):
    # Monotone, bounded encoding; versions themselves remain exact in CCP.
    return watermark / (32.0 + watermark)


class QueryMemory(ResponseMemory):
    def update(self, frame):
        if self.reader is None:
            self.reader = self.observer_path.open()
        record = json.loads(self.reader.readline())
        run, epoch, enabled, terminal, rules = record
        if (
            run != frame["run"]
            or epoch != frame["epoch"]
            or terminal
            or [(rid, wm) for rid, wm, _ in rules] != list(map(tuple, frame["rules"]))
        ):
            raise ValueError("native query observer disagrees with publication")
        self.rule_ids = [rid for rid, _, _ in rules]
        self.rule_features = torch.zeros(len(rules), 32)
        for i, (rid, wm, dirty) in enumerate(rules):
            self.rule_features[i, :3] = torch.tensor(
                [float(dirty), stamp(wm), float(enabled)]
            )
        self.rule_index = {rid: i for i, rid in enumerate(self.rule_ids)}
        updates = frame["updates"]
        last_version = updates[-1][1]["version"] if updates else 0
        self.public_features = torch.zeros(32)
        self.public_features[3:10] = torch.tensor(
            [
                stamp(epoch),
                stamp(run),
                stamp(len(updates)),
                stamp(len(frame["retired"])),
                stamp(len(frame["accepted"])),
                float(bool(updates)),
                stamp(last_version),
            ]
        )
        super().update(frame)

    def close_observer(self):
        if self.reader is not None:
            self.reader.close()

    def graph(self, key):
        v = super().graph(key)
        i = getattr(self, "rule_index", {}).get(key[0])
        return v if i is None else v + self.rule_features[i]

    def context(self):
        return (self.state + self.event + self.public_features).tanh()


def conditioned(a, d, path):
    m = memory(a, d, memory_type=QueryMemory)
    m.observer_path = path
    m.reader = None
    return m


class QueryPage(AddressPage):
    def publication(self, frame):
        super().publication(frame)
        m = self.m
        if isinstance(m, QueryMemory) and m.rule_ids:
            ids = torch.tensor(m.rule_ids) * 2
            idx = self.upload(torch.stack((ids, ids + 1), 1).flatten().int())
            self.graphs[idx] = self.base_graphs[idx] + self.upload(
                m.rule_features.repeat_interleave(2, dim=0)
            )


def setup(a, m, arm, cap):
    marks, rates = models("1M")
    marks.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[0]
    )
    gates = torch.cat([p.flatten() for p in marks.choice.parameters()]).detach()
    marks.choice.load_state_dict(torch.load(a.out / f"{arm}.pt", weights_only=True))
    page = QueryPage(m, marks, rates, Counter())
    page.base_graphs = page.graphs.clone()
    page.lib = code(page.width, "tree-fit")
    page.cap = cap
    page.weights = torch.cat((page.weights, gates.to("mps")))
    marks.resident_page = page
    return marks, rates, page


def offline_memory(a, d, case, arm, source="teacher"):
    if arm in ("B", "D"):
        return conditioned(a, d, a.out / f"state-{case}-{source}.jsonl")
    return memory(a, d)


def online_memory(a, d, dest, arm):
    return (
        conditioned(a, d, dest / "state.jsonl") if arm in ("B", "D") else memory(a, d)
    )
