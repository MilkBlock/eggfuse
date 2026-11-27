"""Signed native execution. All repetition attribution reads the closed native ledger."""

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_egg_catalogue import install
from joint_cell_corpus import folder
from joint_cell_train import fitted
from partner_index_worlds import args
from prefix_train import make
from region_bake import linked
from trigger_execution import ExecutionTrace
from variable_binding_execution import SparsePolicy
from variable_completion import CompletionPolicy


class Uniform(CompletionPolicy):
    def generate(self, w, s, rng, slots):
        start = perf_counter()
        if self.slot_limit is not None:
            slots = min(slots, self.slot_limit - self.count["offered"])
        self.count["offered"] += slots
        by_type = defaultdict(list)
        for p in s["ports"]:
            by_type[p[3]].append(p[0])
        families = defaultdict(list)
        for t in s["menu"]:
            r = w.layouts[t][0][0]
            if all(by_type[tab] for tab in w.roles[r]):
                families[r].append(t)

        def choose(xs):
            return xs[rng.integers(len(xs))]

        out = []
        if families:
            roots = list(families)
            for _ in range(slots):
                r = choose(roots)
                out.append(
                    (
                        choose(families[r]),
                        tuple(choose(by_type[tab]) for tab in w.roles[r]),
                    )
                )
        self.decode_s += perf_counter() - start
        return out


class UniformDecoder:
    """Use Page's exact leaf exclusion with uniform, statically typed factors."""

    @staticmethod
    def prepare(w):
        pass

    def state(self, w, s):
        tables = torch.tensor([p[3] for p in s["ports"]], dtype=torch.long)
        present = set(tables.tolist())
        families = {}
        for j, tid in enumerate(s["menu"]):
            rid = w.layouts[tid][0][0]
            if all(t in present for t in w.roles[rid]):
                families.setdefault(rid, []).append(j)
        return dict(
            menu=s["menu"],
            families=families,
            root_lp=torch.zeros(len(families)).log_softmax(0),
            tables=tables,
            refs=[p[0] for p in s["ports"]],
            has_complete_domain=bool(families),
        )

    def address(self, w, m, tid, prefix):
        rid = w.layouts[tid][0][0]
        allowed = m["tables"] == w.roles[rid][len(prefix)]
        return (
            torch.zeros(len(allowed)).masked_fill(~allowed, -torch.inf).log_softmax(0)
        )

    def variant_prob(self, w, m, rid, first):
        return torch.zeros(len(m["families"][rid])).log_softmax(0)


class PageIds:
    def __init__(self):
        self.pages = []

    def append(self, row):
        self.pages.append([r[0] for r in row[2]])


def classify(pages, entries):
    last = {}
    accepted = set()
    tot = Counter()
    details = []
    for page, ids in enumerate(pages):
        for uid in ids:
            r = entries[uid]
            named = (r["tid"], tuple(r["refs"]))
            prior = last.get(named)
            kind = (
                "first_name"
                if prior is None
                else "same_page"
                if prior["page"] == page
                else "cross_submit"
            )
            # Physical comparison uses the native root and versioned references. A new
            # complete name can still use precisely the same entry as another Higher.
            entry = (r["rid"], tuple(r["refs"]))
            other_refs = r["status"] == "duplicate" and entry not in accepted
            row = dict(r, page=page, kind=kind, native_duplicate_new_refs=other_refs)
            if prior is not None:
                row["previous_uid"] = prior["uid"]
                row["changed_run"] = prior["run"] != r["run"]
                if row["changed_run"] and r["effective_ops"] > 0:
                    tot["changed_run_repeat_productive"] += 1
            if r["status"] == "accepted":
                accepted.add(entry)
            tot[kind] += 1
            tot[f"{kind}_{r['status']}"] += 1
            tot["native_duplicate_new_refs"] += int(other_refs)
            details.append(row)
            last[named] = row
    return dict(tot), details


def run(a, case):
    d = folder(a)
    ir, align = egg(a, case)
    donor = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    arms = os.environ.get("JC_ARMS", "random original sparse expanded feedback").split()
    for budget in os.getenv("JC_BUDGETS", "slots paid full").split():
        for draw in map(int, os.getenv("JC_DRAWS", "193 307").split()):
            for arm in arms:
                multiple = arm in (
                    "small",
                    "expanded",
                    "feedback",
                    "replay",
                    "sweep",
                    "blind",
                    "iid",
                )
                seeds = (
                    (71, 113)
                    if multiple and budget == "full" and not os.getenv("JC_REP")
                    else (71,)
                )
                for seed in seeds:
                    if os.getenv("JC_SEED") and seed != int(os.environ["JC_SEED"]):
                        continue
                    stem = (
                        f"timing{os.environ['JC_REP']}"
                        if os.getenv("JC_REP")
                        else "live"
                    )
                    dest = d / f"{stem}-{case}-{budget}-{arm}-{seed}-{draw}.json"
                    if dest.exists():
                        continue
                    net = (
                        fitted(
                            a,
                            case,
                            arm if arm not in ("blind", "iid") else "expanded",
                            seed,
                        )
                        if arm
                        not in (
                            "original",
                            "original_unique",
                            "sparse",
                            "random",
                            "random_unique",
                        )
                        else make(a, "base").eval()
                    )
                    w = World(ir, net.actor, entry_table=None, sides="")
                    install(w, linked(w.prog, donor), "multi")
                    limit = 384 if budget == "slots" else None
                    if arm == "blind":
                        full = net.state
                        net.state = lambda w, s: full(w, dict(s, request_receipts=()))
                    pol = (
                        SparsePolicy(net, limit, a, a.data / case)
                        if arm == "sparse"
                        else (Uniform if arm == "random" else CompletionPolicy)(
                            net, arm not in ("iid", "original", "random"), limit, False
                        )
                    )
                    if arm == "random_unique":
                        pol = CompletionPolicy(UniformDecoder(), True, limit, False)
                    obs = ExecutionTrace()
                    ids = PageIds()
                    result = native(
                        a,
                        w,
                        policy=pol,
                        seed=draw,
                        slots=6,
                        submit_pages=2,
                        receipt_log=ids,
                        receipt_memory=True,
                        rule_state=True,
                        execution_trace=obs,
                        paid_limit=96 if budget == "paid" else None,
                        reference=align,
                    )
                    tally, events = classify(ids.pages, obs.entries)
                    from joint_cell_corpus import write_rows

                    write_rows(dest.with_suffix(".pkl.gz"), events)
                    dest.write_text(
                        json.dumps(
                            dict(
                                result,
                                case=case,
                                budget=budget,
                                arm=arm,
                                seed=seed,
                                draw=draw,
                                duplicates=tally,
                                decoder=pol.count,
                                decode_s=pol.decode_s,
                            )
                        )
                    )
                    print(dest.name, result["covered"], result["ops"], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
