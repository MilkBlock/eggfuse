"""Native CCP rollouts from learned weights. Iterate runs in reverse order on the second block."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import torch

from data_scale_train import LEVELS, SEEDS
from metal_scaling import CASES, execute_one


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument(
        "--devices",
        nargs="+",
        default=["cpu"],
        choices=["cpu", "mps", "resident", "scalar", "matched", "stream"],
    )
    p.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    p.add_argument("--levels", nargs="+", type=int, default=LEVELS)
    p.add_argument("--sizes", nargs="+", default=["100K", "1M"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--wait-library", type=Path)
    p.add_argument("--profile-index", action="store_true")
    a = p.parse_args()
    if a.profile_index and a.devices != ["stream"]:
        p.error("--profile-index requires --devices stream")
    counter = None
    if a.wait_library:
        import ctypes

        lib = ctypes.CDLL(str(a.wait_library.resolve()))
        if not lib.install_wait_counter():
            raise RuntimeError("could not install Metal wait counter")
        counter = lib.command_buffer_waits
        counter.restype = ctypes.c_uint64
        before = counter()
        torch.ones(8, device="mps").sum().item()
        if counter() <= before:
            raise RuntimeError("Metal wait calibration failed")
    torch.set_num_threads(1)
    jobs = [
        (case, n, seed, size, device)
        for case in a.cases
        for n in a.levels
        for seed in a.seeds
        for size in a.sizes
        for device in a.devices
    ]
    for block in range(a.blocks):
        for case, n, seed, size, device in jobs if block == 0 else reversed(jobs):
            arg = SimpleNamespace(
                out=a.out / f"s{seed}",
                data=a.data,
                actor=a.actor,
                profile_index=a.profile_index,
                timing_prefix=(
                    "profile-" if a.profile_index else "meter-" if counter else ""
                )
                + device
                + "-",
                wait_counter=counter,
                device_gnn=False,
                seconds=480,
                resident=device == "resident",
                stream_device=device == "stream",
                matched=device in ("scalar", "matched"),
            )
            execute_one(
                arg,
                size,
                f"n{n}",
                {
                    "resident": "mps",
                    "stream": "mps",
                    "scalar": "mps",
                    "matched": "cpu",
                }.get(device, device),
                case,
                block,
            )


if __name__ == "__main__":
    main()
