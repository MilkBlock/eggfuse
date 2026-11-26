"""Collect the pinned high-recall Cell Stream's actual accepted tapes on training programs."""

import json
from collections import Counter

import torch

from ccp_v01 import Client
from continuation_audit import arguments
from discrete_reference import Reference
from transaction_native import execute


def observed_client():
    rejected = {}
    accepted = Counter()

    class Observed(Client):
        def _record(self, op, refs, response, run):
            actual = super()._record(op, refs, response, run)
            begin = 0
            for row, verdict in zip(op, response, strict=True):
                end = int(row[4])
                code = int(verdict[1])
                key = (run, accepted[run], code)
                if code and key not in rejected:
                    rejected[key] = {
                        "rule": int(row[2]),
                        "refs": refs[begin:end, :3].tolist(),
                        "response": verdict.tolist(),
                    }
                accepted[run] += int(code == 0)
                begin = end
            return actual

    return Observed, rejected


if __name__ == "__main__":
    a = arguments().parse_args()
    torch.set_num_threads(1)
    store = a.out.resolve() / "reference-stream"
    for case in ("grammar-benefit-fork-17118", "sum"):
        client, rejected = observed_client()
        policy = Reference(original_order=True)
        policy.client_type = client
        r = execute(a.data, case, study=policy, seconds=1800, series=str(store))
        (store / (case + "-negative.json")).write_text(
            json.dumps([[*k, v] for k, v in rejected.items()]) + "\n"
        )
        if r["termination"] != "schedule_end":
            raise ValueError(r["termination"])
        (store / (case + ".json")).write_text(json.dumps(r) + "\n")
        print(case, r["runs"], r["committed_tokens"], flush=True)
