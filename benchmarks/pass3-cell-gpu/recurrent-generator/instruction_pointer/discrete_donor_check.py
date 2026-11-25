"""Certify the negative donor by executing both plans to the native endpoint before labeling it."""

from tempfile import TemporaryDirectory

from discrete_cells import from_q
from discrete_draft import Cell, plan
from discrete_rollout import Policy
from recursive_train import read
from transaction_native import execute


def certify(root, d, u, m, out):
    q = from_q(read(d / "tape.json")["requests"][0])
    results = {}

    class Named(Policy):
        def __init__(self, high):
            self.high = high
            self.done = False
            self.m = m
            self.waiting = []
            self.confirmed = m.pub

        def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
            rows, _, retired, _ = pub
            m.update(
                dict(
                    rules=frame["rules"],
                    retired=[dict(token=int(t), op=int(o)) for t, o in retired],
                    updates=[
                        (dict(token=int(r[0]), op=int(r[1])), rd.store.visible[int(r[0]), int(r[1])])
                        for r in rows
                    ],
                )
            )
            self.resume_programs(frame, pub, txn, stats)
            if not self.done and q.rule in dict(frame["rules"]):
                self.send(plan([Cell(q.rule, q.refs, self.high)]), txn, stats)
                self.done = True

    from latent_cell_flow import Published

    for high in (False, True):
        m.pub = Published(m.enc)
        with TemporaryDirectory(dir=out) as tmp:
            r = execute(root, d.name, study=Named(high), series=tmp)
        results[str(high)] = dict(
            terminal=r["state_sha"],
            effective=r["signed_ops"],
            paid=r["paid"],
            verdicts=r["verdicts"],
            work={k: r["work"].get(k, 0) for k in ("instantiated", "higher_completed", "suffix_rejected")},
        )
    a, b = results["False"], results["True"]
    if (
        a["terminal"] != b["terminal"]
        or a["effective"] != b["effective"]
        or b["paid"] <= a["paid"]
        or b["work"]["suffix_rejected"] != 1
    ):
        raise ValueError(results)
    return results
