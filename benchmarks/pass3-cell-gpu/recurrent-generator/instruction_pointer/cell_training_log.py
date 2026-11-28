"""Queue sample-level CPU scalars. The training process never imports the dashboard SDK."""

import hashlib
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from time import time_ns


class TrainingLog:
    def __init__(self, file, config):
        self.file = Path(file)
        self.events = queue.SimpleQueue()
        self.error = None
        self.thread = threading.Thread(
            target=self._write, daemon=True, name="cell-metrics"
        )
        self.thread.start()
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            commit = None
        self.git_commit = commit
        sources = [
            Path(__file__).with_name(name)
            for name in (
                "cell_training_log.py",
                "scaling_fit.py",
                "joint_cell_sweep.py",
            )
        ]
        source_sha = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        }
        self.events.put(
            {
                "kind": "config",
                "git_commit": commit,
                "source_sha256": source_sha,
                "pid": os.getpid(),
                "started_ns": time_ns(),
                **config,
            }
        )

    def _write(self):
        try:
            with self.file.open("a", encoding="utf-8") as out:
                while (event := self.events.get()) is not None:
                    out.write(
                        json.dumps(event, allow_nan=False, separators=(",", ":")) + "\n"
                    )
                    out.flush()
        except (OSError, ValueError) as exc:
            self.error = exc

    def log(self, metrics, step):
        self.events.put({"kind": "metrics", "step": step, "metrics": metrics})

    def finish(self):
        self.events.put({"kind": "finish"})
        self.events.put(None)
        self.thread.join()
        if self.error:
            import warnings

            warnings.warn(f"Cell tracking journal unavailable: {self.error}")


def start_log(dst, base, cfg, seed, archive, registered):
    if os.getenv("CELL_TRAIN_LOG", "1") == "0":
        return None
    return TrainingLog(
        dst / (base + "-live.jsonl"),
        dict(
            config=cfg,
            seed=seed,
            archive=archive,
            registered=registered,
            checkpoint_directory=str(dst.absolute()),
            model=base,
        ),
    )
