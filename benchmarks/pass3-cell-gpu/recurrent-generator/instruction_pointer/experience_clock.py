"""Offline align actual acknowledged publications to common wall-clock budgets."""

from discovery_score import write_csv
from discovery_states import cli, read, replay
from recursive_coverage import Target, snapshot
from recursive_train import folder


def curves(a):
    rows = []
    tmp = a.out / "clock-state.json"
    for case in a.cases:
        d = folder(a.data, case)
        reference = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, tmp)[0],
        )
        initial = reference.match(snapshot(a.data, d, "reference", "-", 0, tmp)[0])
        for file in sorted(a.out.glob(f"native/*/*/native-address/{case}/*/run.json")):
            v = read(file)
            tape = file.parent / (case + "-stream-multi") / "issued.json"
            setup = v["cold_wall"] - v["wall"]
            seed, draw = file.relative_to(a.out).parts[1:3]
            cache = {0: (0, 0)}
            for seconds in (0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128):
                arrived = next(
                    (
                        t
                        for t in reversed(v["trace"])
                        if t["elapsed"] + setup <= seconds
                    ),
                    {},
                )
                r = arrived.get("run", 0)
                if r not in cache:
                    audit = replay(a, case, tape, r, "--export", tmp, "--ept")
                    ept = audit["ept"]
                    cache[r] = (
                        len(reference.match(read(tmp)) - initial),
                        sum(ept["signed_external"]) + sum(ept["signed_internal"]),
                    )
                n, ops = cache[r]
                if r == v["runs"]:
                    assert (n, ops) == (v["covered"], v["signed_ops"])
                rows.append(
                    {
                        "case": case,
                        "arm": v["method"],
                        "seed": seed,
                        "draw": draw,
                        "block": v["block"],
                        "seconds": seconds,
                        "run": r,
                        "paid": arrived.get("paid", 0),
                        "effective": ops,
                        "facts": n,
                        "reference": v["reference"],
                    }
                )
    write_csv(a.out / "clock.csv", rows)


if __name__ == "__main__":
    curves(cli().parse_args())
