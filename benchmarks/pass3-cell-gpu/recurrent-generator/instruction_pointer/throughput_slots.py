"""Observe the empty-draft address path after the single normal GPU readback."""

import gzip
import json
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import torch
from address_runtime import code, native
from coverage_eval import choices
from discovery_native import configure
from discovery_states import cli, read
from query_environment import online_memory

REASONS = ("empty_typed_table", "missing_named_projection", "selected_row_wrong_table")


class SlotLog:
    def __init__(self, stream=None, retain_page=False):
        self.stream = stream
        self.totals = Counter()
        self.failures = Counter()
        self.run = None
        self.ordinal = 0
        self.retain_page = retain_page
        self.last_page = None

    def record(self, row):
        if self.stream is not None:
            self.stream.write(json.dumps(row, separators=(",", ":")) + "\n")

    def draw(self, page, raw, items):
        complete = []
        slots = []
        for row in raw.tolist():
            ident, reason = divmod(row[0], 1 + 3 * page.slots)
            if ident < 1 or (row[1] >= 0) != (reason == 0):
                raise ValueError("missing slot trace or wrong outcome")
            tid = ident - 1
            if reason:
                depth, why = divmod(reason - 1, 3)
                self.failures[tid, depth, why] += 1
                self.totals[REASONS[why]] += 1
            else:
                depth = len(page.m.roles[tid // 2])
                complete.append(tid)
            refs = []
            if self.stream is not None or self.retain_page:
                for i in range(depth):
                    gid, _, v = row[2 + 3 * i : 5 + 3 * i]
                    if gid <= 0:
                        raise ValueError(
                            "unexpected local reference in an empty independent page"
                        )
                    owner, op = page.addresses[gid]
                    refs.append((owner, op, v))
            slots.append([tid, reason, refs])
        if complete[::-1] != [2 * x.cell.rule + int(x.cell.higher) for x in items]:
            raise ValueError("attempt stream does not reproduce inserted draft")
        self.totals.update(
            slot_attempts=len(slots),
            selected_templates=len(slots),
            complete=len(items),
            draw_calls=1,
        )
        if self.retain_page:
            self.last_page = slots
        self.record(["draw", self.run, self.ordinal, slots])
        self.ordinal += 1

    def quota(self, goal, complete):
        n = min(goal, complete)
        self.totals.update(returned=n, over_goal=complete - n, shortfall=goal - n)
        self.record(["quota", self.run, self.ordinal, goal, complete, n])

    def summary(self):
        c = self.totals
        if c["complete"] + sum(c[r] for r in REASONS) != c["slot_attempts"]:
            raise ValueError("unaccounted mark")
        return dict(
            counts=dict(c),
            failures=[[t, d, REASONS[w], n] for (t, d, w), n in self.failures.items()],
        )


def instrument(page, log):
    page.lib = code(page.width, "tree-fit", True)
    page.slot_observer = log
    return page


def trace(a):
    base = a.out
    for arm in a.arms:
        dest = base / "observed" / arm
        dest.mkdir(parents=True, exist_ok=True)
        logs = {}
        with ExitStack() as stack:

            def mem(args, d, where, name):
                m = online_memory(args, d, where, "D")
                m.audit_case = d.name
                return m

            def make(args, m, name, cap):
                log = SlotLog(
                    stack.enter_context(
                        gzip.open(
                            dest / (m.audit_case + ".jsonl.gz"), "wt", compresslevel=1
                        )
                    )
                )
                logs[m.audit_case] = log
                w = SimpleNamespace(**(vars(a) | {"out": a.weights}))

                def setup(*_):
                    marks, rates, page = choices(w, m, arm, cap, 9633)
                    return marks, rates, instrument(page, log)

                models = configure(args, m, "D", cap, setup)
                publish = m.on_page_publication

                def update(frame):
                    log.run = frame["run"]
                    publish(frame)

                m.on_page_publication = update
                return models

            cfg = SimpleNamespace(
                **(
                    vars(a)
                    | dict(
                        out=dest,
                        arms=[arm],
                        blocks=1,
                        pages=2,
                        cap=16,
                        seconds=300,
                        generation_seed=536,
                    )
                )
            )
            native(cfg, make, mem)
        for case, log in logs.items():
            suffix = Path("native-address") / case / (arm + "-k16-p2-b0") / "run.json"
            run = read(dest / suffix)
            ref = read(a.weights / "native/9633/536" / suffix)
            if (
                any(
                    run[k] != ref[k]
                    for k in ("facts", "state_sha", "paid", "signed_ops", "verdicts")
                )
                or log.totals["slot_attempts"] != ref["device"]["neural_slot_attempts"]
                or log.totals["returned"] + run["work"].get("lowered_suffix", 0)
                != run["paid"]
            ):
                raise ValueError(
                    "observer changed execution or returned Token was not issued"
                )
            log.totals["paid_higher_suffix"] = run["work"].get("lowered_suffix", 0)
            log.totals["paid"] = run["paid"]
            (dest / (case + ".json")).write_text(json.dumps(log.summary(), indent=2))


if __name__ == "__main__":
    p = cli()
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--arms", nargs="+", default=["initial", "dual-witness"])
    a = p.parse_args()
    torch.set_num_threads(1)
    trace(a)
