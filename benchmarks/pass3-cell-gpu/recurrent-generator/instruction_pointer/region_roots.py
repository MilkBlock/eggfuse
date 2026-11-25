"""Offline exact-next intervention on saved neural prefixes. Nothing returns to the online sampler."""

import argparse
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_train import binary, folder, read
from scaling_bake import save


def audit(root, out):
    reports = {}
    for file in sorted((out / "signed").glob("*-routes32.0.E.empty.json")):
        case = file.name.split("-routes32.")[0]
        certificate = read(out / "transfer.json")[case]["certificate"]
        if not certificate:
            continue
        rid = certificate["root"]
        saved = read(file)
        tape = saved["tape"]
        rows = []
        with TemporaryDirectory(dir=out) as tmp:
            prefix = Path(tmp) / "prefix.json"

            def fork(source, run):
                save(
                    prefix,
                    dict(
                        source,
                        requests=[q for q in source["requests"] if q["run"] < run],
                        repair_events=[q for q in source["repair_events"] if q["visible_from_run"] <= run],
                    ),
                )
                return json.loads(
                    subprocess.check_output(
                        [
                            binary(root),
                            "replay",
                            folder(root, case) / "program.json",
                            prefix,
                            "time",
                            str(run - 1),
                            "--audit-next-proofs",
                        ]
                    )
                )

            teacher = read(folder(root, case) / "tape.json")
            witness = next(q for q in teacher["requests"] if q["token"] == certificate["witness"][0])
            positive = fork(teacher, witness["run"])
            teacher_count = sum(q["run"] == witness["run"] and q["rule"] == rid for q in teacher["requests"])
            actual_count = sum(q["rule"] == rid for q in positive)
            if not teacher_count or actual_count != teacher_count:
                raise ValueError(
                    ("teacher positive-control binding count mismatch", case, teacher_count, actual_count)
                )
            for run, scheduled in saved["schedule"]:
                if rid not in scheduled:
                    continue
                exact = fork(tape, run)
                chosen = [q for q in exact if q["rule"] == rid]
                if any(q["run"] != run for q in exact):
                    raise ValueError("wrong next Run")
                rows.append(
                    dict(run=run, all_next_proofs=len(exact), root_bindings=[q["parents"] for q in chosen])
                )
        reports[case] = dict(
            root=rid,
            size=certificate["size"],
            runs=rows,
            positive_control=dict(
                run=witness["run"],
                rule_bindings=sum(q["rule"] == rid for q in positive),
                teacher_bindings=teacher_count,
                same_named_witness=any(
                    q["rule"] == rid and q["parents"] == witness["parents"] for q in positive
                ),
            ),
        )
    save(out / "own-prefix-oracle.json", reports)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    audit(a.root, a.out)
