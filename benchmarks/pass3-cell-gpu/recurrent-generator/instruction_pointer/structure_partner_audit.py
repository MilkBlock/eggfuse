"""Post-run exhaustive partner check on the frozen pointer policy's own events."""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

import torch

from protocol_experiment import dump
from recursive_ripsat_study import episode
from recursive_train import binary, folder, read
from structure_runtime import PointerEntries


class RecordPartners(PointerEntries):
    def open_partner(self, r, j, pos, src, target, recent, mem, mode):
        chosen = super().open_partner(r, j, pos, src, target, recent, mem, mode)
        if mode == "Compose":
            if not hasattr(self, "partner_events"):
                self.partner_events = []
            wm = self.rules[r] if mem.rd.iface.rules[r]["metadata"]["seminaive"] else -1
            options = [ref for ref in recent if ref[0] != src[0] and max(src[2], ref[2]) >= wm]
            self.partner_events.append((self.txn.run, r, j, src, options, chosen, len(self.txn.accepted)))
        return chosen

    def audit_partners(self, data, case, work, result):
        tape = read(work / "issued.json")
        order = {q["token"]: i for i, q in enumerate(tape["requests"])}
        boundaries = [0]
        for _, records, _, _ in self.txn.accepted:
            boundaries.append(boundaries[-1] + len(records))
        events = getattr(self, "partner_events", ())
        counts = Counter(events=len(events))
        requests, labels = [], {}
        for i, (run, rule, j, src, options, chosen, issued) in enumerate(events):
            counts["eligible_events"] += int(bool(options))
            for other in options:
                refs = (src, other) if j == 0 else (other, src)
                token = len(requests) + 1
                requests.append(
                    {
                        "run": int(run),
                        "rule": int(rule),
                        "token": token,
                        "parents": [
                            {"address": {"token": int(t), "op": int(o)}, "version": int(v)}
                            for t, o, v in refs
                        ],
                    }
                )
                labels[token] = (i, other == chosen, boundaries[issued])
        probe = work / "named-partners.json"
        dump(probe, dict(tape, requests=requests))
        rep = json.loads(
            subprocess.check_output(
                [
                    binary(data),
                    "replay",
                    folder(data, case) / "program.json",
                    work / "issued.json",
                    "audit",
                    str(result["runs"]),
                    "--recall",
                    probe,
                ]
            )
        )
        verdicts = rep["recall_verdicts"]
        if rep["state_sha"] != result["state_sha"] or rep["unused_recall"] or len(verdicts) != len(requests):
            raise ValueError("incomplete or divergent offline partner replay")
        signs = Counter()
        valid, novel, selected = set(), set(), set()
        for _, token, winner, reason in verdicts:
            signs[reason] += 1
            event, picked, previous = labels[token]
            if reason == "off_reference" or winner is not None:
                valid.add(event)
                if winner is None or order[winner] >= previous:
                    novel.add(event)
                    if picked:
                        selected.add(event)
        return {
            "counts": counts,
            "reasons": signs,
            "fully_checked": len(verdicts),
            "events_with_valid_partner": len(valid),
            "events_with_still_unsigned_partner": len(novel),
            "pointer_picked_still_unsigned": len(selected),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("store", type=Path)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    torch.set_num_threads(1)
    state = torch.load(args.store / "recursive-rl.pt", weights_only=True)
    for case in args.cases:
        row = episode(args.data, args.store, case, "probe", state, True, policy_cls=RecordPartners)
        pointer = read(args.store / f"{case}-pointer-0.json")
        if any(row[k] != pointer[k] for k in ("state_sha", "paid", "open_actions", "signed_ops")):
            raise ValueError("partner audit changed the policy trajectory")
