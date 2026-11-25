"""High-recall Cell Stream with an optional pre-search, one-owner Recipe entry."""

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from discrete_cells import Marks
from discrete_reference import Reference
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from response_study import OLD, arguments, memory
from scaling_bake import save
from transaction_native import execute


class GroupedReference(Reference):
    def __init__(self, m):
        super().__init__(True)
        self.m = m
        self.m.only_group = True
        self.marks = Marks().eval()
        self.marks.load_state_dict(torch.load(OLD / "marks.pt", weights_only=True))
        self.rng = np.random.default_rng(536)

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        rows, _, retired, accepted = pub
        t = perf_counter()
        self.m.update(
            dict(
                updates=[
                    (dict(token=int(t), op=int(p)), rd.store.visible[int(t), int(p)])
                    for t, p, *_ in rows
                ],
                retired=[dict(token=int(t), op=int(p)) for t, p in retired],
                rules=frame["rules"],
                accepted=accepted,
            )
        )
        self.m.state = (self.m.pub.total.float() / 16).asinh().tanh()
        stats["group_memory_seconds"] += perf_counter() - t
        # This supplementary entry gets two attempts per native frame. The full
        # reference Stream still processes every original branch and pays for repeats.
        for _ in range(2):
            cell = self.marks.draw(self.m, self.rng, stats)
            if cell is None:
                continue
            assert len({ref[0] for ref in cell.refs}) == 1
            result = txn.submit(
                [[0, 0, cell.rule, -1, len(cell.refs)]],
                np.array([(*r, -1) for r in cell.refs], dtype=np.int64),
            )
            stats["optional_entry_paid"] += 1
            stats["optional_entry_accepted"] += int(result[0, 1] == 0)
        super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)


@torch.no_grad()
def paired(a):
    d = folder(a.data, a.case)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "ref.json"
        target = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, path)[0],
        )
        initial = target.match(snapshot(a.data, d, "reference", "-", 0, path)[0])
        for block in range(a.blocks):
            for arm in "AB" if block % 2 == 0 else "BA":
                cached = a.out / f"{a.case}__reference-source-order_b1.json"
                if block == 0 and arm == "A" and cached.exists():
                    res = read(cached)
                    if res.get("termination") == "schedule_end" and "facts" in res:
                        save(
                            a.out / f"high-{a.case}-A-b0.json",
                            dict(res, arm=arm, block=block, source=cached.name),
                        )
                        continue
                t = perf_counter()
                policy = (
                    Reference(True) if arm == "A" else GroupedReference(memory(a, d))
                )
                setup = perf_counter() - t
                res = execute(
                    a.data, a.case, study=policy, seconds=a.seconds, series=tmp
                )
                graph = read(Path(tmp) / (a.case + "-stream-multi") / "state.json")
                facts = sorted(target.match(graph) - initial)
                res.pop("trace", None)
                wall = res["wall"] + res["runtime_setup_seconds"] + setup
                res.update(
                    arm=arm,
                    block=block,
                    facts=facts,
                    covered=len(facts),
                    reference=len(target.gold) - len(initial),
                    cold_wall=wall,
                    cold_eps=res["signed_ops"] / wall,
                    setup=setup,
                )
                save(a.out / f"high-{a.case}-{arm}-b{block}.json", res)
                print(
                    a.case,
                    arm,
                    block,
                    len(facts),
                    res["termination"],
                    round(wall, 2),
                    flush=True,
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    paired(arguments())
