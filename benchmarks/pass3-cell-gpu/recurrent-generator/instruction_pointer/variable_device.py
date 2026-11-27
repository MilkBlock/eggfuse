"""Batch the existing unsigned boundary for IID draws at frozen state; native timing is separate."""

import json
from time import perf_counter

import torch

from partner_index_worlds import args
from variable_completion import directory, examples, network


def iid_lengths(head, states, uniform):
    stop = head(states).sigmoid()
    # A slot belongs to the emitted prefix iff every draw through it chose Cell.
    return (
        (uniform >= stop).int().cumprod(1, dtype=torch.int32).sum(1, dtype=torch.int32)
    )


def measure(a):
    d = directory(a)
    n = network(a, 71)
    n.actor.stop.load_state_dict(torch.load(d / "boundary-71.pt", weights_only=True))
    states, _, _, _ = examples(a, n, False)
    device = torch.device("mps")
    head = n.actor.stop.to(device)
    cpu = torch.nn.Linear(32, 1)
    cpu.load_state_dict(head.state_dict())
    results = []
    for batch in (1, 32, 128):
        x = states[:batch].contiguous()
        resident = x.to(device)
        for cap in (3, 16, 64):
            rng = torch.Generator().manual_seed(193)
            u = torch.rand((batch, cap), generator=rng)
            check = iid_lengths(head, resident, u.to(device)).cpu()
            assert torch.equal(check, iid_lengths(cpu, x, u))
            samples = []
            for _ in range(5):
                torch.mps.synchronize()
                t = perf_counter()
                for _ in range(64):
                    iid_lengths(head, resident, torch.rand((batch, cap), device=device))
                torch.mps.synchronize()
                samples.append((perf_counter() - t) / 64)
            results.append(
                {
                    "batch": batch,
                    "capacity": cap,
                    "times": samples,
                    "checked": check.tolist(),
                    "output_bytes": 4 * batch,
                }
            )
    (d / "device.json").write_text(json.dumps(results))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        measure(args())
