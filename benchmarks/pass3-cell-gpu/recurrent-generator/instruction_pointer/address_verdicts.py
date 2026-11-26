"""Native offline recall against actual signed input keys, including alternative certificates."""

import json
import subprocess
from collections import Counter, defaultdict

from recursive_train import binary, folder, read


class Probes:
    def __init__(self, a, case, name, tape_path=None):
        self.data = a.data
        self.case = case
        self.d = folder(a.data, case)
        self.out = a.out / "probes" / name / case
        self.out.mkdir(exist_ok=True, parents=True)
        self.rows = []
        self.info = []
        self.tape_path = tape_path or self.d / "tape.json"
        self.tape = read(self.tape_path)
        self.in_run = {(q["run"], q["token"]) for q in self.tape["requests"]}

    def add(self, r, cell, meta):
        n = len(self.rows) + 1
        self.rows.append(
            {
                "run": r,
                "token": n,
                "rule": cell.rule,
                "parents": [
                    {"address": {"token": o, "op": pc}, "version": v}
                    for o, pc, v in cell.refs
                ],
            }
        )
        self.info.append(meta)

    def check(self):
        p = self.out / "requests.json"
        p.write_text(json.dumps(dict(self.tape, requests=self.rows)))
        report = json.loads(
            subprocess.check_output(
                [
                    binary(self.data),
                    "replay",
                    self.d / "program.json",
                    self.tape_path,
                    "audit",
                    "--recall",
                    p,
                ]
            )
        )
        assert not report["unused_recall"] and len(report["recall_verdicts"]) == len(
            self.rows
        )
        result = [
            (r, self.info[token - 1], owner, reason)
            for r, token, owner, reason in report["recall_verdicts"]
        ]
        (self.out / "verdicts.json").write_text(json.dumps(result) + "\n")
        return result

    def score(self):
        marks = defaultdict(list)
        for r, meta, owner, reason in self.check():
            marks[r].append((meta[0], meta[1], owner, reason))
        rows = []
        for r, records in marks.items():
            for n in (4, 16, 64, 256):
                seen = set()
                higher = set()
                counts = Counter()
                for wave, is_h, owner, reason in records:
                    if wave > n:
                        continue
                    counts[reason] += 1
                    if reason == "match" and (r, owner) in self.in_run:
                        (higher if is_h else seen).add(owner)
                rows.append(
                    {
                        "run": r,
                        "n": n,
                        "semantic": len(seen),
                        "higher_entry_only": len(higher - seen),
                        "responses": dict(counts),
                    }
                )
        return rows
