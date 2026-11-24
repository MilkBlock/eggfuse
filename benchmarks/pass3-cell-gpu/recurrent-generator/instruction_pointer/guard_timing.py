"""Alternate exclusive CYK decoders and check exact/oracle controls per pair."""

import argparse
import json
import subprocess
from pathlib import Path
from time import perf_counter

import torch

from recursive_train import binary, folder, read
from stream_guard import Study
from stream_native import execute


def measure(root, dest):
    case = "cyk801"
    d = folder(root, case)
    sha = read(d / "capture.json")["state_sha"]
    results = []
    for i in range(4):
        pair = {}
        for policy in ("control", "p8") if i % 2 == 0 else ("p8", "control"):
            study = Study(bits=8, symmetric=True) if policy == "p8" else None
            result = execute(
                root,
                case,
                "stream",
                240,
                "multi",
                series=f"guard-timing/{policy}",
                study=study,
            )
            assert result["state_sha"] == sha and result["exact_endpoint"]
            pair[policy] = {
                k: result[k]
                for k in (
                    "paid",
                    "signed_ops",
                    "wall",
                    "eps",
                    "native_verify_seconds",
                    "verification_ipc",
                )
            }
        for mode in ("reference", "replay") if i % 2 == 0 else ("replay", "reference"):
            start = perf_counter()
            out = json.loads(
                subprocess.check_output(
                    [
                        binary(root),
                        mode,
                        d / "program.json",
                        d / "tape.json" if mode == "replay" else "-",
                        "time",
                    ]
                )
            )
            assert out["state_sha"] == sha
            pair[mode] = dict(wall=perf_counter() - start, engine=out["seconds"])
        results.append(pair)
        dest.write_text(json.dumps(results, indent=2) + "\n")
        print(i + 1, pair, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    measure(a.root.resolve(), a.dest)
