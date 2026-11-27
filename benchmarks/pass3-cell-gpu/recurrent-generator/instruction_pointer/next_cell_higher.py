"""Native primitive/mixed teaching tapes and a separate autonomous unseen-layout test."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from address_runtime import native
from address_scores import weight
from coverage_eval import choices
from coverage_examples import pack
from discovery_native import configure
from discovery_states import cli
from discrete_cells import from_q
from discrete_draft import Item
from draft_dispatch import Dispatch
from next_cell_corpus import store_file
from query_environment import QueryMemory
from recursive_train import folder, read
from response_study import memory
from scaling_bake import graph_program, prepare
from transaction_native import execute
from throughput_slots import SlotLog, instrument


def state(a, d, observer):
    unit = read(d / "layouts.json")[0][:-1]
    m = memory(a, d, layout=unit, memory_type=QueryMemory)
    m.observer_path = observer
    m.reader = None
    return m


@torch.no_grad()
def teacher(a, case):
    d = folder(a.data, case)
    tape = read(d / "tape.json")
    proofs = {q["run"]: from_q(q) for q in tape["requests"]}
    if len(proofs) != len(tape["requests"]):
        raise ValueError("controlled teaching trace needs one proof per publication")
    gate = weight(a).to("mps")
    unit = read(d / "layouts.json")[0][:-1]
    for mixed in (False, True):
        dest = a.out / "mixed-teacher" / case / str(int(mixed))
        dest.mkdir(exist_ok=True, parents=True)
        m = state(a, d, dest / "scheduler.jsonl")
        blocks = []

        class Teacher(Dispatch):
            def generate_pages(self, txn, stats, deadline):
                self.advance_event(stats)
                c = proofs.get(txn.run)
                if c is None or (mixed and c.rule in {s[0] for s in unit[1:]}):
                    return
                c = replace(c, higher=mixed and c.rule == unit[0][0])
                s = pack(m, [c], gate, case, txn.run)
                s.update(
                    cells=[c],
                    state=(case, mixed, txn.run),
                    anchor=str(dest),
                    evidence=np.array([4], np.uint8),
                )
                items = [Item(txn.run, c)]
                reply = self.issue(items, txn, stats)
                if reply[txn.run][1] != 0:
                    raise ValueError("teacher reference not reproduced")
                self.consume_reply(items, reply)
                blocks.append(s)

        policy = Teacher(m, None, None, "noop", 1, 1, 1, mode="page")
        try:
            result = execute(
                a.data,
                case,
                study=policy,
                series=str(dest),
                runtime_binary=a.runtime_binary,
                observer_path=m.observer_path,
            )
        finally:
            m.close_observer()
        if (
            not result["exact_endpoint"]
            or result["work"].get("higher_completed", 0) != int(mixed)
            or result["paid"] != len(proofs)
            or result["signed_ops"] != len(proofs)
        ):
            raise ValueError(
                "teaching plan did not reproduce the complete native calculation"
            )
        store_file(
            dest / "targets.pkl.gz",
            dict(index=case, signature=m.enc.cat.int_bake.key(unit), blocks=blocks),
        )


def run(a):
    dest = a.out / "layouts"
    dest.mkdir(exist_ok=True, parents=True)
    shapes = (
        (("line", 4), ("fork", 6), ("fork", 8))
        if a.mode == "teacher"
        else (("fork", 11), ("line", 9))
    )
    cases = []
    for shape, size in shapes:
        name = f"scale-{shape}-{size}-1-82913"
        source = folder(a.data, name).with_suffix(".egg")
        if (
            source.exists()
            and source.read_text() != graph_program(shape, size, 1, 82913)[0]
        ):
            raise ValueError(f"workload name collision: {source}")
        prepare(a.data, a.compiler, dest, shape, size, 1, 82913)
        cases.append(name)
        if a.mode == "teacher":
            teacher(a, name)
    if a.mode == "teacher":
        return
    from next_cell_train import read as load_packet

    seen = {
        p["signature"]
        for path in (a.out / "mixed-teacher").glob("*/*/targets.pkl.gz")
        for p in [load_packet(path)]
    }
    root = a.out
    for seed in a.seeds:
        sub = SimpleNamespace(
            **(
                vars(a)
                | dict(
                    cases=cases,
                    arms=a.arms,
                    blocks=1,
                    cap=16,
                    pages=2,
                    seconds=300,
                    generation_seed={9633: 536, 5003: 1129}[seed],
                    out=root / ("unseen-trace" if a.trace else "unseen") / str(seed),
                )
            )
        )

        def make(cfg, m, arm, cap):
            def page_setup(*_):
                marks, rates, page = choices(a, m, arm, cap, seed)
                if a.trace:

                    class HigherSlots(SlotLog):
                        def draw(self, page, raw, items):
                            super().draw(page, raw, items)
                            for tid, reason, _ in self.last_page:
                                if tid % 2:
                                    page.count["higher_template_draws"] += 1
                                    page.count["higher_fully_bound"] += int(reason == 0)

                    instrument(page, HigherSlots(retain_page=True))
                return marks, rates, page

            marks, rates, page = configure(
                cfg,
                m,
                "D",
                cap,
                neural_setup=page_setup,
            )

            if a.trace:
                sample = page.sample

                def observe(*args):
                    items = sample(*args)
                    page.count["higher_returned"] += sum(i.cell.higher for i in items)
                    return items

                page.sample = observe
            return marks, rates, page

        def make_memory(cfg, d, dest, arm):
            m = state(a, d, dest / "state.jsonl")
            if any(m.enc.cat.int_bake.key(u) in seen for u in m.menu.values()):
                raise ValueError("training topology in unseen control")
            return m

        native(sub, make, make_memory)


if __name__ == "__main__":
    p = cli()
    p.add_argument("mode", choices=["teacher", "test"])
    p.add_argument("--trace", action="store_true")
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--seeds", nargs="+", type=int, default=[9633, 5003])
    p.add_argument("--arms", nargs="+", default=["initial", "ce200", "ce200mixed"])
    torch.set_num_threads(1)
    run(p.parse_args())
