"""Calibrate template issuance on separate programs to 99 percent positive recall."""

import argparse
from pathlib import Path
import numpy as np
import torch
from event_addresses import AddressNet
from protocol_experiment import dump
from recursive_train import folder
from train_event_addresses import examples


def calibrate(root, out, dot):
    model = AddressNet().eval()
    model.load_state_dict(torch.load(out / "events.pt", weights_only=True))
    bins = {k: [] for k in ("boot", "event", "address")}
    for i, d in enumerate([dot, folder(root, "grammar-17120")]):
        x, y, _ = examples(root, d, 20031 + i)
        with torch.no_grad():
            logits = model(torch.from_numpy(x))[:, 0].numpy()
        pos = y[:, 0] > 0
        for name, mask in [
            ("boot", x[:, 28] == 0),
            ("event", (x[:, 28] > 0) & (y[:, 1] < 0)),
            ("address", y[:, 1] >= 0),
        ]:
            bins[name].extend(logits[pos & mask].tolist())
    dump(
        out / "calibration.json",
        {
            k: dict(
                n=len(v),
                threshold=(
                    float(sorted(v)[int(0.01 * (len(v) + 1)) - 1])
                    if int(0.01 * (len(v) + 1))
                    else None
                ),
            )
            for k, v in bins.items()
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "out", "dot"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    calibrate(a.root, a.out, a.dot)
