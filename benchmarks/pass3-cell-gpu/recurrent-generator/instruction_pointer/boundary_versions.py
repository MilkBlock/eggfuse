"""Resolve internal version obligations against real publications and the native first rejection."""

import argparse
from pathlib import Path

from boundary_inputs import CASE, binary, folder, read
from boundary_native import run_graph
from entry_closure import Tape
from scaling_bake import save


def audit(root, out):
    t = Tape(folder(root, CASE), binary(root))
    data = read(out / "boundaries.json")
    result = []
    for row in data:
        if row["label"] != "both_ancestries":
            continue
        r = row["region"]
        timeline = []
        for consumer, slot, reason, (src, pc, v) in r["problems"]:
            q = t.q[src]
            events = t.snap.timeline[src, pc]
            timeline.append(
                dict(
                    src=src,
                    op=pc,
                    producer_run=q["run"],
                    consumer=consumer,
                    slot=slot,
                    consumer_run=t.q[consumer]["run"],
                    requested=v,
                    first=t.snap.version(src, pc, q["run"] + 1),
                    timeline=[e for e in events if e[0] <= t.q[consumer]["run"]],
                )
            )
        trace = run_graph(binary(root), t.folder, out, t.tape, r["runs"][0], r["unit"], r["external"])
        if trace["state_sha"] != r["teacher_only"]["state_sha"]:
            raise ValueError("rejection not reproducible")
        result.append(dict(root=row["root"], timelines=timeline, failed_issued_steps=trace["failure"]))
    save(out / "versions.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    audit(a.root, a.out)
