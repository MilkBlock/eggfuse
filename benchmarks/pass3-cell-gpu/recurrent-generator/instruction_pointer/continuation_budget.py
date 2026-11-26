"""Native effects of the observed execution prefix at exact paid-request cutoffs."""

import json

from ccp_v01 import Client
from recursive_coverage import snapshot
from recursive_train import read


class Logged(Client):
    def _record(self, op, refs, response, run):
        out = super()._record(op, refs, response, run)
        self.activity.extend((run, int(status)) for status in response[:, 1])
        return out


def condition(policy, journal):
    class Current(Logged):
        activity = journal

    policy.client_type = Current


def budget_curve(data, d, out, tape, reference, initial, journal, r):
    original = read(tape)
    assert len(journal) == r["paid"] and sum(s == 0 for _, s in journal) == len(
        original["requests"]
    )
    curves = []
    for budget in (1, 2, 4, 8, 16, 32, 64, 128, 256):
        count = min(budget, len(journal))
        if not count or budget > len(journal):
            stop = r["runs"]
        else:
            stop = journal[count - 1][0]
        k = sum(s == 0 for _, s in journal[:count])
        cut = dict(
            original,
            requests=original["requests"][:k],
            repair_events=[v for v in original["repair_events"] if v["run"] <= stop],
        )
        cp = out / "prefix.json"
        cp.write_text(json.dumps(cut))
        graph, rep = snapshot(
            data, d, "replay", cp, stop, out / "prefix-export.json", ept=True
        )
        assert rep["counts"]["accepted"] == k
        ops = sum(rep["ept"]["signed_external"]) + sum(rep["ept"]["signed_internal"])
        curves.append(
            {
                "budget": budget,
                "paid": count,
                "accepted": k,
                "through_run": stop,
                "facts": len(reference.match(graph) - initial),
                "ops": ops,
            }
        )
        if budget > len(journal):
            assert r["state_sha"] == rep["state_sha"] and ops == r["signed_ops"]
    return curves
