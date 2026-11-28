"""Paired actual complete-token optimizer updates, identical inputs and model state."""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

import torch

from exposure_train import output
from partner_index_worlds import args
from scaling_fit import atomic, train


def benchmark(a):
    out = output(a)
    consumer = os.getenv("CELL_LOG_BENCH_CONSUMER") == "1"
    dest = out / ("swan-logging-sidecar.json" if consumer else "swan-logging-cost.json")
    rows = json.loads(dest.read_text()) if dest.exists() else []
    for pair in range(4):
        for enabled in [False, True] if pair % 2 == 0 else [True, False]:
            if any(x["pair"] == pair and x["enabled"] == enabled for x in rows):
                continue
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                cfg = {"name": "logging-pair", "arm": "A"}
                os.environ["CELL_TRAIN_LOG"] = str(int(enabled))
                live = tmp / "logging-pair-s71-live.jsonl"
                sidecar = None
                if enabled and consumer:
                    py = (
                        Path(
                            os.getenv(
                                "CELL_SWAN_VENV",
                                str(Path.home() / ".local/share/cell-tracking/venv"),
                            )
                        )
                        / "bin/python"
                    )
                    sidecar = subprocess.Popen(
                        [
                            py,
                            "cell_dashboard.py",
                            "journal",
                            "--path",
                            live,
                            "--logdir",
                            tmp / "swanlog",
                        ],
                        stdout=subprocess.DEVNULL,
                    )
                start = perf_counter()
                train(a, cfg, 71, [2048], destination=tmp)
                total = perf_counter() - start
                if sidecar is not None and sidecar.wait(timeout=60) != 0:
                    raise RuntimeError("SwanLab reader failed")
                drain = perf_counter() - start - total
                meta = json.loads(next(tmp.glob("*-t2048.json")).read_text())
                tensors = torch.load(next(tmp.glob("*-t2048.pt")), weights_only=True)
                h = hashlib.sha256()
                for k, v in sorted(tensors.items()):
                    h.update(k.encode())
                    h.update(v.contiguous().numpy().tobytes())
                if enabled:
                    import shutil

                    shutil.copyfile(
                        live, out / f"logging-bench-{int(consumer)}-{pair}.jsonl"
                    )
                rows.append(
                    dict(
                        pair=pair,
                        enabled=enabled,
                        weights=h.hexdigest(),
                        wall=total,
                        sidecar_drain_seconds=drain,
                        **{
                            k: meta[k]
                            for k in (
                                "exposures",
                                "steps",
                                "states",
                                "targets",
                                "seconds",
                                "tokens_per_s",
                                "registered",
                                "connected",
                                "forward_observed",
                                "train_ce",
                            )
                        },
                    )
                )
                if len({r["weights"] for r in rows}) != 1:
                    raise ValueError("training instrumentation changed output weights")
                atomic(dest, rows)
                print("paired", pair, enabled, total, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    benchmark(args())
