"""Offline only: verify physical aliases by changing just one reference in a native fork."""

import hashlib
import json
import os
import pickle
from pathlib import Path

from discrete_draft import Cell
from joint_cell_corpus import folder
from multirule_oracle import fork
from partner_index_worlds import args
from prefix_corpus import folder as old


def run(a, case):
    root = Path(os.environ["ARTIFACT_ROOT"])
    d = folder(a)
    tape = json.loads(
        (root / "multi-association" / case / "audit-0/accepted.json").read_text()
    )
    samples = []
    for s, rid, ts, _ in pickle.loads((old(a) / f"{case}.pkl").read_bytes()):
        ports = {p[0]: (p[3], p[4]) for p in s["ports"]}
        r = s["run"]
        prefix = [q for q in tape["requests"] if q["run"] < r]

        def execute(cs):
            export = d / f"alias-export-{case}.json"
            gs, st = fork(
                a,
                a.data / case,
                d / f"alias-fork-{case}.json",
                tape,
                prefix,
                r,
                cs,
                export=export,
            )
            graph = json.loads(export.read_text())
            return dict(
                gains=gs,
                status=st,
                graph=hashlib.sha256(
                    json.dumps(graph, sort_keys=True).encode()
                ).hexdigest(),
            )

        for refs in ts:
            alias = next(
                (
                    refs[:j] + (p,) + refs[j + 1 :]
                    for j, ref in enumerate(refs)
                    for p in ports
                    if p != ref and ports[p] == ports[ref]
                ),
                None,
            )
            if alias is None:
                continue
            x, y = Cell(rid, refs), Cell(rid, alias)
            base, one, two, both = map(execute, ([], [x], [y], [x, y]))
            ok = (
                one["gains"][0] > 0
                and two["gains"] == one["gains"]
                and both["gains"] == one["gains"] + [0]
                and both["status"]["duplicates"] == 1
                and one["graph"] == two["graph"] == both["graph"] != base["graph"]
            )
            samples.append(
                dict(
                    case=case,
                    run=r,
                    rid=rid,
                    refs=refs,
                    alias=alias,
                    verified=ok,
                    branches=[base, one, two, both],
                )
            )
            break
    (d / f"aliases-{case}.json").write_text(json.dumps(samples))


if __name__ == "__main__":
    run(args(), os.environ["TR_CASE"])
