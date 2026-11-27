"""Single-thread CPU policy and separate exact native timing, by reference graph."""

from time import perf_counter
import torch
import binding_model
from binding_online import trial
from completion_context import read, native
from first_parent import load, options, records


def compare(a):
    binding_model.DEVICE = "cpu"
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    rows = []
    for seed in a.seeds:
        nets = {arm: load(a, seed, arm, "cpu") for arm in ("field", "pool")}
        for n in (4, 16, 32, 64, 256, 1024):
            d = a.previous_binding / "worlds/test" / f"{n:04}-eq10-20001-0"
            goal = len(read(d / "ok.json")["gold"])
            ref = native(a, d, "reference", "-")["state_sha"]
            for block in (0, 1):
                for arm in (
                    ("field", "pool", "exact")
                    if not block
                    else ("exact", "pool", "field")
                ):
                    if arm == "exact":
                        start = perf_counter()
                        result = native(a, d, "reference", "-")
                        wall = perf_counter() - start
                        assert result["state_sha"] == ref
                        row = dict(
                            arm=arm,
                            seed=seed,
                            size=n,
                            paid="",
                            ops=goal,
                            seconds=wall,
                            eps=goal / wall,
                            ept="",
                            graph=ref,
                        )
                    else:
                        row = trial(a, d, arm, nets[arm], seed)
                        row.pop("receipts")
                        assert (row["ops"] == goal) == (row["graph"] == ref)
                    row.update(block=block, goals=goal, coverage=row["ops"] / goal)
                    rows.append(row)
    records(a.out / "cpu.csv", rows)


if __name__ == "__main__":
    compare(options().parse_args())
