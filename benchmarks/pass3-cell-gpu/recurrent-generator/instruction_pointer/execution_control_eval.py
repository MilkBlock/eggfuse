"""Paired independent rollouts with identical frozen Cell marks and native Recipe schedules."""

from collections import Counter
from itertools import product
from time import perf_counter
from types import SimpleNamespace

import torch

from discovery_native import configure
from discovery_states import read, save
from discrete_draft import plan
from draft_dispatch import Dispatch
from execution_control import CONTINUE, SUBMIT, pick, window
from execution_control_data import arguments
from query_environment import online_memory, setup
from recursive_coverage import Target, snapshot
from recursive_train import folder
from transaction_native import execute


class Controlled(Dispatch):
    def __init__(self, *args, control):
        super().__init__(*args, mode="page")
        self.control = control
        self.balance = 0
        self.history = []
        self.publications = []

    def record_publication(self, frame, publication):
        self.publications.append(
            {
                "run": frame["committed_through_run"],
                "updates": len(publication[0]),
                "retired": len(publication[2]),
                "accepted": len(publication[3]),
                "epoch": frame["epoch"],
            }
        )

    def generate_pages(self, txn, stats, deadline):
        page = self.marks.resident_page
        start = len(self.receipts)
        if self.control in ("A", "factored"):
            before = len(self.journal)
            super().generate_pages(txn, stats, deadline)
            batches = [len(j["issued"]) for j in self.journal[before:]]
            history = {
                "reason": "fixed_policy",
                "pages": len(batches),
                "submits": sum(n > 0 for n in batches),
                "actions": [],
                "signed": txn.paid,
            }
        else:

            def generate():
                self.advance_event(stats)
                tick = perf_counter()
                items = page.sample(self.m, (), 1, self.rng, stats)
                stats["sampling_seconds"] += perf_counter() - tick
                stats["stream_pages"] += 1
                stats["final_tokens"] += len(items)
                return [i.cell for i in items]

            def issue(cells):
                # Resident complete-token generation returns named references. No host
                # semantic filtering, sorting, duplicate elimination or proof completion.
                batch = plan(cells)
                replies = self.issue(batch, txn, stats)
                self.consume_reply(batch, replies)
                return [replies[i.uid] for i in batch]

            def choose(x, mask):
                tick = perf_counter()
                action = pick(self.nets["flow"], x, mask)
                stats["control_forward_seconds"] += perf_counter() - tick
                stats["control_forward_calls"] += 1
                return action

            self.balance = min(
                2 if self.control == "C-no-bank" else 6, self.balance + 2
            )
            rows, self.balance, reason = window(
                self.m, self.balance, self.control, choose, generate, issue, deadline
            )
            history = {
                "actions": rows,
                "reason": reason,
                "pages": sum(r["action"] == CONTINUE for r in rows),
                "submits": sum(r["action"] == SUBMIT for r in rows),
                "signed": txn.paid,
            }
        history.update(run=txn.run, receipts=self.receipts[start:])
        self.history.append(history)


@torch.no_grad()
def run(a):
    for block in range(a.blocks):
        jobs = list(product(a.cases, a.arms))
        for case, arm in jobs if block % 2 == 0 else reversed(jobs):
            dest = a.out / "independent" / case / f"{arm}-{a.generation_seed}-{block}"
            dest.mkdir(parents=True, exist_ok=True)
            if (dest / "result.json").exists():
                continue
            d = folder(a.data, case)
            start = perf_counter()
            mem = online_memory(a, d, dest, "A" if arm == "factored" else "D")
            cfg = SimpleNamespace(
                **(
                    vars(a)
                    | {
                        "pages": 6
                        if arm in ("C", "C-no-exit-credit", "C-shuffle")
                        else 2
                    }
                )
            )

            def frozen(cfg, mem, unused, cap):
                cfg.out = a.checkpoint.parent
                return setup(cfg, mem, a.checkpoint.stem, cap)

            marks, rates, page = configure(
                cfg, mem, "factored" if arm == "factored" else "D", a.cap, frozen
            )
            if arm not in ("A", "factored"):
                weights = (
                    "rates-no-exit-credit.pt"
                    if arm == "C-no-exit-credit"
                    else "rates.pt"
                )
                if arm == "C-shuffle":
                    weights = "rates-shuffle.pt"
                rates.load_state_dict(torch.load(a.out / weights, weights_only=True))
            pol = Controlled(
                mem,
                marks,
                {"flow": rates},
                "empty",
                1,
                a.generation_seed,
                2,
                control=arm,
            )
            init = perf_counter() - start
            try:
                v = execute(
                    a.data,
                    case,
                    study=pol,
                    series=str(dest),
                    seconds=300,
                    observer_path=getattr(mem, "observer_path", None),
                    runtime_binary=a.runtime_binary,
                )
            finally:
                if hasattr(mem, "close_observer"):
                    mem.close_observer()
            paid = v["paid"]
            journal = pol.history
            if v["termination"] != "schedule_end" or len(journal) != v["runs"]:
                raise ValueError("incomplete native rollout")
            if len(pol.publications) != len(journal) + 1:
                raise ValueError("missing initial or final publication")
            gold = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, dest / "ref.json")[0],
            )
            initial = gold.match(
                snapshot(a.data, d, "reference", "-", 0, dest / "ref.json")[0]
            )
            facts = sorted(
                gold.match(read(dest / (case + "-stream-multi") / "state.json"))
                - initial
            )
            cold = init + v["runtime_setup_seconds"] + v["wall"]
            result = {
                "case": case,
                "arm": arm,
                "block": block,
                "seed": a.generation_seed,
                "coverage": len(facts) / (len(gold.gold) - len(initial)),
                "facts": facts,
                "reference": len(gold.gold) - len(initial),
                "sha": v["state_sha"],
                "paid": paid,
                "ops": v["signed_ops"],
                "ept": v["ept"],
                "eps": v["signed_ops"] / cold,
                "seconds": cold,
                "controls": v["work"].get("control_forward_calls", 0),
                "control_seconds": v["work"].get("control_forward_seconds", 0),
                "exits": dict(Counter(e["reason"] for e in journal)),
                "pages": sum(e["pages"] for e in journal),
                "submits": sum(v["transaction_sizes"].values()),
                "seals": v["work"]["seals"],
                "advances": 0,
                "device": dict(page.count),
            }
            save(
                dest / "history.json",
                {"windows": journal, "publications": pol.publications},
            )
            save(dest / "result.json", result)
            print(
                case,
                arm,
                block,
                len(facts),
                paid,
                round(cold, 2),
                result["exits"],
                flush=True,
            )


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--generation-seed", type=int, default=536)
    p.add_argument("--arms", nargs="+", default=["factored", "A", "B", "C"])
    torch.set_num_threads(1)
    run(p.parse_args())
