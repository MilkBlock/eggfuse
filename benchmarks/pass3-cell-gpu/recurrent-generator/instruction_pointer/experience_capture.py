"""Record decisions and native feedback on training programs without controlling dispatch."""

import json
from collections import Counter, defaultdict
from types import SimpleNamespace

import torch

from ccp_v01 import Client
from cell_transaction import STATUS
from discovery_sampling import encode
from discovery_states import cli, save
from draft_dispatch import Dispatch
from parallel_fit import TRAIN
from query_environment import conditioned, setup
from recursive_train import folder, read
from transaction_native import execute


@torch.no_grad()
def capture(a, case):
    dest = a.out / "experience" / case / "self"
    dest.mkdir(parents=True, exist_ok=True)
    m = conditioned(a, folder(a.data, case), dest / "state.jsonl")
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    marks, rates, page = setup(cfg, m, "D", 16)
    pages = defaultdict(list)
    responses = []
    sample = page.sample

    def record(mem, draft, steps, rng, stats):
        before = stats["mark_draws"]
        items = sample(mem, draft, steps, rng, stats)
        row = {
            "run": policy.current,
            "page": len(pages[policy.current]),
            "context": [
                mem.last,
                mem.event.tolist(),
                mem.state.tolist(),
                mem.context().tolist(),
            ],
            "paid_before": len(responses),
            "attempts": stats["mark_draws"] - before,
            "slot_budget": page.cap,
            "draft": [encode(i.cell) for i in draft],
            "generated": [encode(i.cell) for i in items],
        }
        pages[policy.current].append(row)
        return items

    class RecordClient(Client):
        def _record(self, ops, refs, reply, run):
            result = super()._record(ops, refs, reply, run)
            last = 0
            for row, r in zip(ops, reply, strict=True):
                end = int(row[4])
                responses.append(
                    {
                        "run": run,
                        "id": int(row[1]),
                        "epoch": int(self.epoch),
                        "rule": int(row[2]),
                        "refs": refs[last:end, :3].tolist(),
                        "status": STATUS[int(r[1])],
                        "response": r.tolist(),
                    }
                )
                last = end
            return result

    policy = Dispatch(m, marks, {"flow": rates}, "empty", 1, 536, 2, mode="page")
    page.sample = record
    policy.client_type = RecordClient
    try:
        result = execute(
            a.data,
            case,
            study=policy,
            series=str(dest),
            seconds=300,
            runtime_binary=a.runtime_binary,
            observer_path=m.observer_path,
        )
    finally:
        m.close_observer()
    expected = read(
        a.out.parent / "coverage-loss" / "failures" / case / "receipts.json"
    )
    assert (
        result["termination"] == "schedule_end"
        and len(responses) == result["paid"] == expected["paid"]
    )
    assert result["state_sha"] == expected["state_sha"]
    assert len({r["id"] for r in responses}) == len(responses)
    assert dict(Counter(r["status"] for r in responses)) == result["verdicts"]
    # The dispatcher supplies the actual request IDs for generated cells, including
    # repeated physical tokens. Native continuations have their own ID and no page slot.
    issued = {r[1]: r for r in policy.receipts}
    receipts = {r["id"]: r for r in responses}
    offsets = defaultdict(int)
    for journal in policy.journal:
        if not journal["uids"] and not pages[journal["run"]]:
            continue
        idx = offsets[journal["run"]]
        row = pages[journal["run"]][idx]
        offsets[journal["run"]] += 1
        assert journal["rules"] == [v[0] for v in row["generated"]]
        row["uids"] = journal["uids"]
        row["issued_uids"] = journal["issued"]
    for rr in pages.values():
        for i, row in enumerate(rr):
            end = rr[i + 1]["paid_before"] if i + 1 < len(rr) else len(responses)
            span = []
            for res in responses[row["paid_before"] : end]:
                if res["run"] != row["run"]:
                    break
                if res["id"] in issued:
                    span.append(issued[res["id"]])
            assert [x[2] for x in span] == row["issued_uids"]
            row["request_ids"] = [x[1] for x in span]
            for ident in row["request_ids"]:
                receipts[ident]["page"] = row["page"]
    with (dest / "state.jsonl").open() as stream:
        epochs = {row[0]: row[1] for row in map(json.loads, stream)}
    for run, rr in pages.items():
        for row in rr:
            row["epoch"] = epochs[run]
    save(dest / "pages.json", [r for rr in pages.values() for r in rr])
    save(dest / "responses.json", responses)
    save(dest / "run.json", result)
    print(case, len(responses), sum(map(len, pages.values())), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = cli().parse_args()
    for case in sorted({case for case, _ in TRAIN}):
        capture(a, case)
    torch.mps.synchronize()
