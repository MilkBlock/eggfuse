"""Exercise entry closure with published repair-event evidence outside the selected catalog."""

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from entry_closure import Tape, named
from receipt_bake import read, save
from receipt_takeover import replay_many


def check(folder, binary):
    tape = Tape(folder, binary)
    repair = {ev["token"] for ev in read(folder / "tape.json")["repair_events"]}
    counts = Counter()
    example = None
    for r, roots in tape.by_rule.items():
        inputs = [
            ts
            for ts in roots
            if any(named(a)[0] in repair for a in tape.q[ts[0]]["parents"])
        ]
        counts["root_commits_reading_repair"] += len(inputs)
        if not inputs:
            continue
        unit = tape.rules.root(r)
        for step in tape.rules.extensions(unit, Counter()):
            for root in inputs:
                ts = tape.extend(root, step)
                if ts is None:
                    continue
                counts["executable_two_step_instances"] += 1
                if example is None:
                    with TemporaryDirectory() as tmp:
                        p = Path(tmp) / "layout.json"
                        save(p, [[unit[0], step]])
                        result = replay_many(
                            folder,
                            binary,
                            p,
                            [(0, ts)],
                            tape.tape,
                            read(folder / "capture.json"),
                        )
                    example = dict(steps=ts, wiring=[unit[0], step], native=result)
    return dict(counts=counts, example=example)


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("root", "binary", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    save(a.out, {name: check(a.root / name, a.binary) for name in a.cases})
