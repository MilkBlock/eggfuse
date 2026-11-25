"""Specialize a Recipe entry on its seminaive obligation before B expands it.

Only version metadata indexes B's existing candidate posting.  Every candidate
that can still supply the delta obligation remains in original visitation order.
"""

from time import perf_counter

import numpy as np
import torch

from entry_model import scores
from recursive_train import read
from ripsat_layout import signatures
from structure_runtime import StructureEntries


class CostBake:
    def __init__(self, owner, entries, oracle=None):
        self.owner = owner
        self.entries = entries
        self.oracle = oracle
        self.cached = {}
        self.run = None
        self.active = False

    def choose(self, mem, r, j, ix, woke, wm):
        self.active = False
        if not woke or (r, j) not in self.entries or not mem.rd.iface.rules[r]["metadata"]["seminaive"]:
            return
        order = mem.order(r, j)
        if len(order) < 2:
            return
        owner = self.owner
        decision_start = perf_counter()
        run = owner.txn.run
        if run != self.run:
            self.cached.clear()
            self.run = run
        source = mem.bank(mem.roles[r][j])
        if self.oracle is None:
            normal = owner.code(mem, r, j)
            code = normal.copy()
            # Existing descriptor fields: size of the obligation, arity of the
            # residual. Same B scoring head, both options use the same operands.
            code[-2:] = [len(order) / 8, 1.0]
            logits = scores(
                owner.model, torch.from_numpy(source.vec[ix]), torch.from_numpy(np.stack([normal, code]))
            )
            chosen = logits.argmax(1).numpy().astype(bool)
            if owner.exploration is not None:
                explore = owner.exploration.random(len(ix)) < 0.20
                chosen[explore] = owner.exploration.integers(2, size=int(explore.sum()))
            owner.count["cost_option_scores"] += 2 * len(ix)
        else:
            targets = self.oracle.get((run, r, j), ())
            chosen = np.array([tuple(source.rows[i]) in targets for i in ix], bool)
            owner.count["oracle_address_probes"] += len(ix)
        owner.action_counts["CostBake"] += int(chosen.sum())
        owner.action_counts["CostPrimitive"] += int((~chosen).sum())
        owner.count["cost_choice_seconds"] += perf_counter() - decision_start
        if not chosen.any():
            return
        self.active = True
        self.selected = np.zeros(int(ix.max()) + 1, bool)
        self.selected[ix] = chosen
        self.cut = 0
        for d in range(len(order) - 1, 0, -1):
            bank = mem.bank(mem.roles[r][order[d]])
            owner.count["cost_version_summaries"] += 1
            if len(bank.versions) and bank.versions[-1] >= wm:
                self.cut = d
                break

    def roots(self, ix):
        if self.active and self.cut == 0:
            self.owner.count["cost_closed_root_prefixes"] += int(self.selected[ix].sum())
            return ix[~self.selected[ix]]
        return ix

    def window(self, mem, r, order, d, paths, window, wm):
        if not self.active or self.cut != d:
            return window
        required = self.selected[paths[:, 0]].copy()
        for i in range(1, d):
            required &= mem.bank(mem.roles[r][order[i]]).rows[paths[:, i], 2] < wm
        if not required.any():
            return window
        post, start, n = window
        bank = mem.bank(mem.roles[r][order[d]])
        key = (id(bank), id(post), wm)
        if key not in self.cached:
            build_start = perf_counter()
            listing = np.arange(len(bank.rows)) if post is None else post
            fresh = bank.rows[listing, 2] >= wm
            self.cached[key] = (
                np.concatenate((listing, listing[fresh])),
                np.r_[0, fresh.cumsum()],
                len(listing),
            )
            self.owner.count["cost_index_positions"] += len(listing)
            self.owner.count["cost_index_seconds"] += perf_counter() - build_start
        listing, cumulative, offset = self.cached[key]
        lo = cumulative[start]
        fresh = cumulative[start + n] - lo
        self.owner.count["cost_window_prefixes"] += int(required.sum())
        self.owner.count["cost_window_positions_removed"] += int((n[required] - fresh[required]).sum())
        return listing, np.where(required, lo + offset, start), np.where(required, fresh, n)


class LearnedCostEntries(StructureEntries):
    mode = "learned"

    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        manifest = read(store / "cost-book.json")
        sig = signatures(program)
        recipes = {(s, j) for s, j in manifest["entries"]}
        entries = {
            (r, j)
            for r, s in enumerate(sig)
            for j in range(len(program["recipe"]["rules"][r]["interface"]["rows"]))
            if (s, j) in recipes
        }
        if self.mode == "wide":
            entries = {
                (r, j)
                for r, rule in enumerate(program["recipe"]["rules"])
                if rule["metadata"]["seminaive"]
                for j in range(len(rule["interface"]["rows"]))
            }
        oracle = None
        if self.mode != "learned":
            path = store / (program["recipe"]["sha256"] + "-" + self.mode + ".npz")
            oracle = {}
            for run, r, j, t, pc, v in np.load(path)["events"]:
                oracle.setdefault((run, r, j), set()).add((t, pc, v))
        self.cost_bake = CostBake(self, entries, oracle)


class OracleCostEntries(LearnedCostEntries):
    mode = "oracle"


class WideCostOracle(LearnedCostEntries):
    mode = "wide"


class SingleCostEntries(LearnedCostEntries):
    mode = "single"

    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        from cost_profile import CostProfile

        self.cost_profile = CostProfile()
        self.store = store

    def audit_partners(self, data, case, work, result):
        return self.cost_profile.save(data, self.store, case, work, result, "-single")
