"""Independent Cell Event -> Primitive or compiled entry, using B's named parent path."""

import argparse
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch

from deep_event_boundary import FullTemplates
from entry_model import Family, scores
from event_addresses import pages
from event_generator import EventGenerator
from event_templates import BranchNet
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute


class Entries(FullTemplates):
    def __init__(self, program, store, weights):
        self.program = program
        self.manifest = read(store / "catalog.json")
        self.model = BranchNet().eval()
        self.model.load_state_dict(torch.load(weights, weights_only=True))
        self.family = None
        self.expected = set()
        self.waiting = []

    def start(self, rd, pub, txn, rules, stats):
        if self.family is None:
            self.family = Family(rd, self.program, self.manifest)
            self.cat = SimpleNamespace(units=self.family.units)
        super().start(rd, pub, txn, rules, stats)
        self.covered_rules = {r: rows for r, rows in self.done.items() if rows}
        self.covered_indices = {}
        self.count["receipt_index_records"] += sum(
            map(len, self.covered_rules.values())
        )

    def choose(self, r, j, ix, mem, woke):
        self.mem = mem
        self.choice = {}
        menu = self.family.menu.get(r)
        if not menu:
            return
        x = (
            mem.bank(mem.roles[r][j]).vec[ix]
            if j >= 0
            else np.zeros((len(ix), 16), np.float32)
        )
        logits = scores(
            self.model, torch.from_numpy(x), torch.from_numpy(self.family.codes[r, j])
        )
        actions = logits.argmax(1).tolist()
        for idx, k in zip(ix, actions, strict=True):
            if k:
                self.choice[int(idx)] = menu[k - 1]
        self.count["joint_terminal_scores"] += len(ix) * (1 + len(menu))
        self.count["primitive_terminal_choices"] += len(ix) - len(self.choice)
        self.count["entry_terminal_choices"] += len(self.choice)
        self.count["held_entry_choices"] += sum(
            u in self.family.held for u in self.choice.values()
        )

    def begin(self, uid, row, tok, txn):
        # Every boundary role is an operand of the root. No additional bind() calls.
        self.count["higher_started"] += 1
        self.count["held_entry_starts"] += int(uid in self.family.held)
        self.expected.add(tok)
        boundary = dict(enumerate(map(tuple, row)))
        self.waiting.append((uid, boundary, [tok], {}, 1))

    def proven(self, mem, r, order):
        key = (r, order)
        if key not in self.covered_indices:
            covered = defaultdict(set)
            for refs in self.covered_rules[r]:
                positions = []
                for role in order:
                    t, pc, v = refs[role]
                    bank = mem.bank(mem.roles[r][role])
                    k = bank.positions.get((t, pc))
                    self.count["receipt_position_probes"] += 1
                    if k is None or bank.rows[k, 2] != v:
                        break
                    positions.append(k)
                else:
                    covered[tuple(positions[:-1])].add(positions[-1])
            self.covered_indices[key] = covered
        return self.covered_indices[key]

    def uncovered_events(self, mem, r, j, ix):
        seen = self.proven(mem, r, (j,))[()]
        self.count["receipt_event_checks"] += len(ix)
        left = ix[[int(i) not in seen for i in ix]]
        self.count["proven_event_branches_skipped"] += len(ix) - len(left)
        return left

    def uncovered(self, mem, r, order, parents, post, start, count):
        # Stable posting order makes exact, accepted positions searchable in
        # this already-selected bucket. No field comparison or proof discovery.
        visited = self.proven(mem, r, tuple(order))
        segments = []
        owners = []
        for i, (p, lo, n) in enumerate(zip(parents, start, count, strict=True)):
            self.count["receipt_prefix_checks"] += 1
            end = lo + n
            excluded = []
            for k in visited.get(tuple(p), ()):
                if post is None:
                    pos = k
                else:
                    pos = lo + np.searchsorted(post[lo:end], k)
                    self.count["receipt_posting_probe_bound"] += int(n).bit_length() + 1
                    if pos >= end or post[pos] != k:
                        continue
                if lo <= pos < end:
                    excluded.append(pos)
            self.count["proven_candidate_positions_skipped"] += len(excluded)
            for pos in [*sorted(excluded), end]:
                if pos > lo:
                    owners.append(i)
                    segments.append((lo, pos - lo))
                lo = pos + 1
        if segments:
            lo, n = np.asarray(segments, dtype=np.int64).T
            owners = np.asarray(owners)
            for i, pos in pages(lo, n):
                yield owners[i], pos


def run(data, store, case, arm, rep):
    p = EventGenerator(data, case, Path("run-recall/cell-events"), "B")
    d = folder(data, case)
    if arm != "B":
        weights = (
            store / "entry.pt"
            if arm == "trained"
            else Path("run-recall/cell-events/template.pt")
        )
        p.higher = Entries(read(d / "program.json"), store, weights)
    series = f"entry-first/{arm}/{rep}"
    result = execute(data, case, study=p, seconds=600, series=series)
    work = data / series / (case + "-stream-multi")
    align = work / "align.json"
    target = Target(
        read(d / "program.json"), snapshot(data, d, "reference", "-", None, align)[0]
    )
    initial = target.match(snapshot(data, d, "reference", "-", 0, align)[0])
    result.update(
        facts=len(target.match(read(work / "state.json")) - initial),
        reference=len(target.gold) - len(initial),
    )
    result.pop("trace")
    dump(store / f"{case}-{arm}-{rep}.json", result)
    print(
        case,
        arm,
        rep,
        result["termination"],
        result["facts"],
        result["paid"],
        result["wall"],
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+", choices=("B", "frozen", "trained"))
    p.add_argument("--rep", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        run(a.data, a.store, a.case, arm, a.rep)
