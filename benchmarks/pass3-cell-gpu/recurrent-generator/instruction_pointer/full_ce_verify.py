"""Verify durable training weights, actual exposure sets and the native metrics in the report."""

import gzip
import hashlib
import json
import math
import os
import pickle
import platform
import sys
from collections import Counter
from pathlib import Path

import torch

from int_parameters import digest
from scaling_campaign import REPORT


def checksum(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run():
    raw = Path(os.environ["PARTNER_INDEX_OUT"]) / "full-ce-scaling"
    state = json.loads((raw / "campaign.json").read_text())
    groups = dict(state["groups"])
    for p in (REPORT / "size-controls").glob("*.json"):
        groups[p.stem] = json.loads(p.read_text())
    manifest = {}

    def record(p):
        key = str(p.relative_to(raw))
        if key not in manifest:
            manifest[key] = checksum(p)
        return manifest[key]

    for p in raw.iterdir():
        if p.is_file() and not p.name.startswith("."):
            record(p)
    for name, m in groups.items():
        base = raw / "fits"
        if record(base / (name + ".pt")) != m["weights_sha"]:
            raise ValueError(f"weight digest mismatch: {name}")
        config = json.loads((base / (name + ".json")).read_text())
        if any(
            config[k] != m[k]
            for k in ("config", "steps", "exposures", "targets", "states", "train_ce")
        ):
            raise ValueError(f"fit metadata mismatch: {name}")
        record(base / (name + ".json"))
        exposures = base / (name + ".seen.gz")
        with gzip.open(exposures, "rb") as f:
            seen = pickle.load(f)
        if (
            len(seen) != m["states"]
            or sum(map(len, seen.values())) != m["targets"]
            or not (m["targets"] <= m["exposures"])
        ):
            raise ValueError(f"training membership mismatch: {name}")
        record(exposures)
    for p in (raw / "fits").glob("*-resume.pt"):
        record(p)
    counts = Counter()
    for p in sorted((raw / "eval").glob("*.json")):
        result = json.loads(p.read_text())
        record(p)
        rows = result["runs"]
        if result["mode"] == "outer":
            artifact = raw / (p.stem + "-ledger.json.gz")
            with gzip.open(artifact, "rt") as f:
                ledgers = {(v["case"], v["cap"], v["seed"]): v for v in json.load(f)}
            if len(ledgers) != len(rows):
                raise ValueError("missing held-out native ledger")
            for r in rows:
                entry = ledgers[r["case"], r["cap"], r["seed"]]
                if (digest(entry["responses"]) != r["response_sha"]
                        or len(entry["generated"]) != r["stats"].get("neural_tokens", 0)):
                    raise ValueError("held-out named requests or native responses differ")
        for case in {r["case"] for r in rows}:
            pairs = [(r["cap"], r["seed"]) for r in rows if r["case"] == case]
            if len(set(pairs)) != len(pairs):
                raise ValueError(f"duplicate paired native measurement: {p.name}")
            if result["mode"] in ("validation", "outer", "selection") and set(
                pairs
            ) != {(c, s) for c in (16, 32, 64, 128, 256) for s in (193, 307)}:
                raise ValueError(f"incomplete paid-budget curve: {p.name}")
        for r in rows:
            n, cap = r["paid"], r["cap"]
            if not (
                0 <= n <= cap and cap - n == r["shortfall"] and n == r["stats"]["paid"]
            ):
                raise ValueError("native paid budget or truncation differs")
            if not (r["covered"] == len(r["facts"]) and r["covered"] <= r["reference"]):
                raise ValueError("reference fact count differs")
            for measured, expected in (
                (r["ept"], r["ops"] / max(1, n)),
                (r["eps"], r["ops"] / r["wall"]),
                (r["coverage"], r["covered"] / r["reference"]),
            ):
                if not math.isclose(measured, expected):
                    raise ValueError("native metric cannot be reconstructed")
            if result["mode"] not in ("intervention", "inner-intervention") and r[
                "intervention"
            ].get("intervened_pages", 0):
                raise ValueError("offline intervention in autonomous measurement")
            counts[result["mode"]] += 1
    for p in (raw / "logs").glob("*.log"):
        record(p)
    for p in (raw / "seen-foundation").glob("*.json"):
        record(p)
    (REPORT / "artifacts.sha256").write_text(
        "".join(f"{h}  {k}\n" for k, h in sorted(manifest.items()))
    )
    (REPORT / "integrity.json").write_text(
        json.dumps(
            {
                "registered_groups_verified": len(groups),
                "native_trials": counts,
                "artifacts": len(manifest),
                "manifest_sha256": checksum(REPORT / "artifacts.sha256"),
                "configuration_lock": state["locked"],
            },
            indent=1,
        )
        + "\n"
    )
    binaries = {}
    for key in ("CELL_REPLAY", "CELL_COMPILER"):
        path = Path(os.environ[key]).resolve()
        binaries[key] = {"path": str(path), "sha256": checksum(path)}
    (REPORT / "runtime.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "executable": sys.executable,
                "torch": str(torch.__version__),
                "os": platform.platform(),
                "neural_device": "cpu",
                "torch_threads_per_trial": 1,
                "native": binaries,
                "artifact_root": os.environ["ARTIFACT_ROOT"],
                "cell_data": os.environ["CELL_DATA"],
            }, indent=2
        ) + "\n"
    )


if __name__ == "__main__":
    run()
