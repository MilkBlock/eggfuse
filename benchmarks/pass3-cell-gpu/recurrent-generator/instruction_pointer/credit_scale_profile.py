"""Measure explicit readbacks and instrument actual Metal command buffer waits on a replay sample."""

import ctypes
import json
import tempfile
from pathlib import Path

import torch

from credit_scale_buffer import collect
from credit_scale_fit import load_shard
from discovery_states import cli

if __name__ == "__main__":
    p = cli()
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    lib = ctypes.CDLL(str(a.library))
    lib.command_buffer_waits.restype = ctypes.c_uint64
    if not lib.install_wait_counter():
        raise RuntimeError("wait instrumentation unavailable")
    before = lib.command_buffer_waits()
    torch.ones(3, device="mps").sum().item()
    if lib.command_buffer_waits() <= before:
        raise RuntimeError("counter calibration failed")
    root = a.out
    a.out = Path(tempfile.mkdtemp(prefix="profile-", dir=root))
    a.first, a.stop, a.lanes, a.cap, a.branches = 0, 6, 6, 256, [2]
    start = lib.command_buffer_waits()
    collect(a)
    torch.mps.synchronize()
    count = lib.command_buffer_waits() - start
    dest = next(a.out.glob("collection-*.json"))
    v = json.loads(dest.read_text())
    for f in (a.out / "buffer").glob("*.json.gz"):
        x, y = load_shard(f), load_shard(root / "buffer" / f.name)
        assert x["terminal"] == y["terminal"]
        assert [(e["generated"], e["response"]) for e in x["events"]] == [
            (e["generated"], e["response"]) for e in y["events"]
        ]
    v.update(command_buffer_waits=count, includes_setup_and_final_barrier=True)
    (root / "metal-profile.json").write_text(json.dumps(v, indent=2) + "\n")
    print(v)
