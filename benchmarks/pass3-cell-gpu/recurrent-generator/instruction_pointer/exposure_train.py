"""Fork the existing 100K optimizer, then advance the same state across exposure milestones."""
import gzip
import hashlib
import json
import os
import pickle
import shutil
from pathlib import Path

import torch

from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import atomic, train


def output(a):
    directory(a)
    path = a.out / "continuation-exposure"
    path.mkdir(exist_ok=True)
    return path


def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run(a):
    arm = os.getenv("EXPOSURE_ARM", "local")
    group = os.getenv("EXPOSURE_DATA", "A")
    seed = int(os.getenv("CELL_SEED", "71"))
    stem = f"{arm}-s{seed}"
    source = directory(a) / "fits"
    out = output(a)
    dest = out / group
    dest.mkdir(exist_ok=True)
    meta = source / (stem + "-t100000.json")
    weights = source / (stem + "-t100000.pt")
    resume = source / (stem + "-resume.pt")
    info = json.loads(meta.read_text())
    cfg = info["config"]
    receipt = {"start": 100000, "seed": seed, "config": cfg, "data": group,
               "archive": info["archive_sha"], "weights_sha256": sha(weights),
               "initial_optimizer_file_sha256": sha(resume)}
    extra = out / (group + "-data.pkl.gz")
    if group != "A":
        receipt["added_data_sha256"] = sha(extra)
    own = dest / resume.name
    manifest = dest / (stem + "-start.json")
    if manifest.exists() and json.loads(manifest.read_text()) != receipt:
        raise ValueError("training lineage or augmented corpus changed")
    if not manifest.exists():
        saved = torch.load(resume, weights_only=False)
        model = torch.load(weights, weights_only=True)
        if (saved["config"] != cfg or saved["bank"] != info["archive_sha"]
                or saved["progress"][4:6] != (100000, info["steps"])
                or not saved["opt"]["state"] or saved["model"].keys() != model.keys()
                or any(not torch.equal(saved["model"][k], v) for k, v in model.items())):
            raise ValueError("optimizer or weights do not match the recorded 100K checkpoint")
        tmp = own.with_suffix(".copy")
        shutil.copyfile(resume, tmp)
        tmp.replace(own)
        atomic(manifest, receipt)
    def extend(pool, net):
        from exposure_data import extend_pool
        with gzip.open(extra, "rb") as f:
            extend_pool(a, pool, net, pickle.load(f))
    caps = list(map(int, os.environ["CELL_MILESTONES"].split()))
    train(a, cfg, seed, caps, destination=dest, extend_pool=extend if group != "A" else None)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
