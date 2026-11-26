"""Offline construction and verification of context-specific address equivalence classes."""

import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path

import torch

from address_twins import propose
from address_verdicts import Probes
from discrete_cells import from_q
from metal_scaling import CASES
from parallel_budget import args
from parallel_fit import TRAIN
from recursive_train import folder, read


def arguments():
    p = args()
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--runtime-binary", type=Path, required=True)
    return p


def tape(a, case, source):
    return (
        folder(a.data, case) / "tape.json"
        if source == "teacher"
        else a.corpus / "reference-stream" / (case + "-stream-multi") / "issued.json"
    )


def probe_dir(a, case, source, held):
    return (
        a.audit / "probes/same-key" / case
        if held
        else a.out / "probes" / ("train-" + source) / case
    )


def groups(a, case, source, held):
    base = probe_dir(a, case, source, held)
    originals = {q["token"]: q for q in read(tape(a, case, source))["requests"]}
    rows = read(base / "requests.json")["requests"]
    result = defaultdict(set)
    for q, (run, (gold, slot, _), owner, reason) in zip(
        rows, read(base / "verdicts.json"), strict=True
    ):
        original = originals[gold]
        assert run == original["run"] == q["run"]
        a0, a1 = from_q(original), from_q(q)
        assert a0.rule == a1.rule and [
            i for i, (x, y) in enumerate(zip(a0.refs, a1.refs, strict=True)) if x != y
        ] == [slot]
        if reason == "match" and owner == gold:
            result[run, a0].add(a1)
    return result


def prepare(a):
    a.out.mkdir(parents=True, exist_ok=True)
    assert set(c for c, _ in TRAIN).isdisjoint(CASES)
    manifest = []
    for held, sources in [(False, TRAIN), (True, [(c, "teacher") for c in CASES])]:
        for case, source in sources:
            d = folder(a.data, case)
            state = a.out / f"state-{case}-{source}.jsonl"
            replay = subprocess.run(
                [
                    a.runtime_binary,
                    "replay",
                    d / "program.json",
                    tape(a, case, source),
                    "audit",
                    "--memory",
                    os.devnull,
                ],
                check=True,
                capture_output=True,
                env={**os.environ, "EGGFUSE_QUERY_OBSERVER": str(state)},
            )
            report = json.loads(replay.stdout)
            assert report["counts"]["accepted"] == len(
                read(tape(a, case, source))["requests"]
            )
            if not held:
                probe = Probes(a, case, "train-" + source, tape(a, case, source))
                propose(a, case, source, probe)
                probe.check()
            g = groups(a, case, source, held)
            manifest.append(
                dict(
                    case=case,
                    source=source,
                    held=held,
                    augmented_groups=len(g),
                    verified_variants=sum(map(len, g.values())),
                    state_sha=report["state_sha"],
                )
            )
            print(manifest[-1], flush=True)
    (a.out / "witnesses.json").write_text(json.dumps(manifest, indent=2) + "\n")


def verify(a):
    manifest = read(a.out / "witnesses.json")
    for row in manifest:
        case, source = row["case"], row["source"]
        base = probe_dir(a, case, source, row["held"])
        report = json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    folder(a.data, case) / "program.json",
                    tape(a, case, source),
                    "audit",
                    "--recall",
                    base / "requests.json",
                ]
            )
        )
        assert report["state_sha"] == row["state_sha"] and not report["unused_recall"]
        saved = read(base / "verdicts.json")
        assert len(saved) == len(report["recall_verdicts"])
        for run, token, owner, reason in report["recall_verdicts"]:
            r, _, checked_owner, checked_reason = saved[token - 1]
            assert (r, checked_owner, checked_reason) == (run, owner, reason)
        row["rechecked"] = len(saved)
    (a.out / "witness-check.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    p = arguments()
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    (verify if a.verify else prepare)(a)
