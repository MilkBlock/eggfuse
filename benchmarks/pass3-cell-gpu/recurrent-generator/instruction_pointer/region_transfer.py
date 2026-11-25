"""Post-freeze offline transfer audit. Does not feed the decoder or modify the catalog."""

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from entry_closure import Tape
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from region_bake import DONORS, linked
from scaling_bake import recursive_named, save

HELD = ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119")


def audit(root, out):
    counts = {}
    for case in (*DONORS, *HELD):
        t = Tape(folder(root, case), binary(root))
        rows = []
        best = None
        for r, u in linked(t.program, read(out / "menu.json")).items():
            composed = recursive_named(u)
            assert [(rid, stage, list(w)) for rid, stage, w in u] == composed
            prior = Counter(src for _, _, w in u for src in {a for a, b in w if a >= 0})
            live = t.by_rule[r]
            prefix = [len(live)]
            for step in u[1:]:
                live = [v for ts in live if (v := t.extend(ts, step))]
                prefix.append(len(live))
            if live and (best is None or len(u) > len(best[0])):
                best = u, live[0]
            rows.append(
                dict(
                    root=r,
                    size=len(u),
                    external=len(u[0][2]),
                    prefix=prefix,
                    forks=sum(v > 1 for v in prior.values()),
                    joins=sum(len({a for a, b in w if a >= 0}) > 1 for _, _, w in u),
                )
            )
        certificate = None
        if case in HELD and best:
            with TemporaryDirectory(dir=out) as tmp:
                path = Path(tmp) / "unit.json"
                save(path, [best[0]])
                try:
                    result = replay_many(
                        t.folder, binary(root), path, [(0, best[1])], t.tape, read(t.folder / "capture.json")
                    )
                except ValueError as e:
                    result = dict(error=str(e))
                certificate = dict(
                    root=best[0][0][0],
                    size=len(best[0]),
                    external=len(best[0][0][2]),
                    witness=best[1],
                    result=result,
                )
        counts[case] = dict(
            layouts=rows,
            certificate=certificate,
            hashes={
                f: hashlib.sha256((t.folder / f).read_bytes()).hexdigest()
                for f in ("program.json", "memory.jsonl", "tape.json", "capture.json")
            },
        )
    save(out / "transfer.json", counts)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    audit(a.root, a.out)
