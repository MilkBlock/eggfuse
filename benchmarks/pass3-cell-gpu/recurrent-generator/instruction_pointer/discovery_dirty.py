"""Observe generation and native responses without changing the model or the CCP envelope."""

import json
import os
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import torch

from ccp_v01 import Client
from cell_transaction import STATUS
from discovery_states import cli, issued, save
from draft_dispatch import Dispatch
from query_environment import online_memory, setup
from recursive_train import folder
from transaction_native import execute


def audit(a, case):
    dest = a.out / "dirty" / case
    dest.mkdir(parents=True, exist_ok=True)
    m = online_memory(a, folder(a.data, case), dest, "D")
    args = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    marks, rates, page = setup(args, m, "D", 16)
    states = {}
    events = []
    current = []
    origins = {}
    sample = page.sample

    def traced(mem, source, steps, rng, stats):
        r = p.current
        if r not in states:
            states[r] = [
                mem.last,
                mem.event.tolist(),
                mem.state.tolist(),
                mem.context().tolist(),
            ]
        result = sample(mem, source, steps, rng, stats)
        for x in result:
            i = mem.rule_index[x.cell.rule]
            origins[id(x)] = (r, int(mem.rule_features[i, 0]))
        return result

    page.sample = traced

    class Observe(Dispatch):
        def issue(self, items, txn, stats):
            current.extend(origins.pop(id(x), None) for x in items)
            result = super().issue(items, txn, stats)
            assert not current
            return result

    class Log(Client):
        def _record(self, op, refs, response, run):
            v = super()._record(op, refs, response, run)
            for row, reply in zip(op, response, strict=True):
                rid = int(row[2])
                source = current.pop(0) if current else None
                raw = m.rule_features[m.rule_index[rid]]
                clean = bool(raw[2]) and not bool(raw[0])
                assert (STATUS[int(reply[1])] == "untriggered_rule") == clean
                events.append(
                    [run, int(row[1]), rid, source, int(raw[0]), STATUS[int(reply[1])]]
                )
            return v

    p = Observe(m, marks, {"flow": rates}, "empty", 1, 536, 2, mode="page")
    p.client_type = Log
    try:
        with patch.dict(
            os.environ, EGGFUSE_ADMISSION_OBSERVER=str(dest / "native-gates.csv")
        ):
            x = execute(
                a.data,
                case,
                study=p,
                series=str(dest),
                seconds=240,
                runtime_binary=a.runtime_binary,
                observer_path=m.observer_path,
            )
    finally:
        m.close_observer()
    _, old = issued(a, case)
    assert x["state_sha"] == old["state_sha"] and x["verdicts"] == old["verdicts"]
    native = [
        tuple(map(int, line.split(",")))
        for line in (dest / "native-gates.csv").read_text().splitlines()
    ]
    frames = {
        r: (epoch, en)
        for r, epoch, en, _, _ in map(
            json.loads, (dest / "state.jsonl").read_text().splitlines()
        )
    }
    for (r, i, rid, source, observed, status), (
        rr,
        ii,
        rule,
        epoch,
        enabled,
        actual,
    ) in zip(events, native, strict=True):
        assert (r, i, rid, observed) == (rr, ii, rule, actual) and frames[r] == (
            epoch,
            bool(enabled),
        )
        if source is not None and source[0] == r:
            assert source[1] == actual
    assert len(events) == old["paid"]
    save(dest / "contexts.json", states)
    save(dest / "admissions.json", events)
    print(
        case,
        len(events),
        Counter(
            ("suffix" if not src else "same" if src[0] == r else "cross")
            for r, _, _, src, _, v in events
            if v == "untriggered_rule"
        ),
        flush=True,
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = cli().parse_args()
    for case in a.cases:
        audit(a, case)
