"""Summarize paid CCP requests, actual accepted operations and reference fact identities."""

import argparse
import csv
from pathlib import Path

from protocol_experiment import dump, digest
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read


def summarize(root, source, dest):
    rows = []
    assert read(source / "catalog.json") == read(dest / "catalog.json")
    for case in ("fact", "loopfact", "sum-divisors"):
        d = folder(root, case)
        align = source / "reference.json"
        target = Target(
            read(d / "program.json"),
            snapshot(root, d, "reference", "-", None, align)[0],
        )
        seed = target.match(snapshot(root, d, "reference", "-", 0, align)[0])

        def facts(arm):
            return (
                target.match(
                    read(root / f"deep-ripsat/{arm}/0/{case}-stream-multi/state.json")
                )
                - seed
            )

        base = facts(0)
        for arm in (0, 1, 3, 2):
            hit = facts(arm)
            for group in ("", "size-pairs"):
                for path in sorted((source / group).glob(f"{case}-{arm}-*.json")):
                    dct = read(path)
                    w = dct["work"]
                    assert len(hit) == dct["facts"]
                    assert (
                        dct["state_sha"]
                        == read(source / f"{case}-{arm}-0.json")["state_sha"]
                    )
                    rows.append(
                        dict(
                            case=case,
                            arm=arm,
                            cohort=group or "independent",
                            rep=path.stem.split("-")[-1],
                            facts=len(hit),
                            new_vs_B=len(hit - base),
                            lost_vs_B=len(base - hit),
                            reference=dct["reference"],
                            state_sha=dct["state_sha"],
                            terminal=dct["termination"],
                            runs=dct["runs"],
                            commits=dct["committed_tokens"],
                            signed_ops=dct["signed_ops"],
                            neural_proof_requests=dct["proof_paid"]
                            - w.get("lowered_steps", 0),
                            ccp_paid=dct["paid"],
                            visits=w["visits"],
                            higher_scores=w.get("higher_event_scores", 0),
                            attempts=w.get(
                                "higher_attempts", w.get("higher_started", 0)
                            ),
                            starts=w.get("higher_started", 0),
                            completed=w.get("completed_deep", 0),
                            internal_paid=w.get("lowered_steps", 0),
                            replaced=w.get("replaced_requests", 0),
                            duplicates=dct["verdicts"].get("duplicate", 0),
                            wall=dct["wall"],
                            ept=dct["ept"],
                            eps=dct["eps"],
                        )
                    )
    for group in ("trained-4096", "matched-4096"):
        for path in sorted((source / group).glob("*-2-0.json")):
            run = read(path)
            dump(dest / group / path.name, run)
    with (dest / "runs.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    dump(
        dest / "identities.json",
        dict(
            build=digest(binary(root)),
            weights=digest(source / "event-gnn.pt"),
            original_catalog=digest(source / "catalog.json"),
            compact_catalog=digest(dest / "catalog.json"),
            baseline=digest(Path("run-recall/cell-events/template.pt")),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "source", "dest"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    summarize(a.root, a.source, a.dest)
