"""Measure synchronized host-to-host cost of the actual two trained decision modules."""

import argparse
import csv
import statistics
from pathlib import Path
from time import perf_counter_ns

import torch

from metal_scaling import SIZES, models


@torch.inference_mode()
def measure(directory, destination):
    torch.set_num_threads(1)
    _, data = torch.load(directory / "held.pt", weights_only=True)
    with destination.open("w") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(
            [
                "size",
                "module",
                "rows",
                "device",
                "block",
                "median_us",
                "p90_us",
                "cpu_mps_max_abs",
                "cpu_mps_decisions_differ",
                "comparison_rows",
            ]
        )
        for size in SIZES:
            weights = torch.load(
                directory / (size + "-large") / "weights.pt", weights_only=True
            )
            cpu_pair, gpu_pair = models(size), models(size)
            for cpu, gpu, params in zip(cpu_pair, gpu_pair, weights, strict=True):
                cpu.load_state_dict(params)
                gpu.load_state_dict(params)
            for kind, cpu, gpu in (
                ("mark", cpu_pair[0].choice, gpu_pair[0].choice),
                ("rate", cpu_pair[1], gpu_pair[1]),
            ):
                gpu.to("mps")
                for batch in (1, 128):
                    inputs = data[kind][0][:batch].contiguous()
                    a, b = cpu(inputs), gpu(inputs.to("mps")).cpu()
                    error = float((a - b).abs().max())
                    decision_a, decision_b = (
                        (a >= 0, b >= 0)
                        if kind == "mark"
                        else (a.argmax(1), b.argmax(1))
                    )
                    different = int((decision_a != decision_b).sum())
                    for block, devices in enumerate((("cpu", "mps"), ("mps", "cpu"))):
                        for device in devices:
                            net = gpu if device == "mps" else cpu
                            timings = []
                            for it in range(23):
                                start = perf_counter_ns()
                                net(inputs.to(device)).cpu()
                                if it >= 3:
                                    timings.append((perf_counter_ns() - start) / 1000)
                            writer.writerow(
                                [
                                    size,
                                    kind,
                                    batch,
                                    device,
                                    block,
                                    statistics.median(timings),
                                    sorted(timings)[17],
                                    error,
                                    different,
                                    len(inputs),
                                ]
                            )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("csv_file", type=Path)
    args = p.parse_args()
    measure(args.directory, args.csv_file)
