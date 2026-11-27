"""Exhaust the 16 physical pairs offline and separate native binding and guard mass."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import torch
import numpy as np
from address_scores import weight
from completion_context import directory, frames, native, read, write
from coverage_examples import pack
from discovery_score import packet
from discovery_sampling import Domain
from discovery_states import cli
from query_fit import log_paths


@torch.no_grad()
def audit(a):
    gate = weight(a).to("mps").eval()
    models = {}
    for seed in (9633, 5003, 1777):
        for arm in ("initial", "A", "B", "C", "small"):
            net = weight(a).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            models[seed, arm] = net
    result = []
    for i in (80, 81, *range(90, 106)):
        for order in (0, 1):
            d = directory(a, 4, "pair", i, order)
            m = frames(a, d)
            try:
                for line in (d / "frames.jsonl").read_text().splitlines():
                    m.update(json.loads(line))
                dom = Domain(m)
                cells = [dom.decode(k) for k in range(dom.size)]
                s = pack(m, cells, gate, "offline-only", 2)
                with TemporaryDirectory() as tmp:
                    probe = Path(tmp) / "pairs.json"
                    tape = read(d / "prefix.json")
                    write(
                        probe,
                        dict(
                            tape,
                            requests=[packet(c, 2, k + 1) for k, c in enumerate(cells)],
                        ),
                    )
                    rep = native(
                        a, d, "replay", d / "verified.json", 2, "--recall", probe
                    )
                labels = {
                    k - 1: why for r, k, _, why in rep["recall_verdicts"] if r == 2
                }
                assert (
                    len(labels) == len(cells) == 16
                    and sorted(labels.values()).count("guard") == 1
                    and list(labels.values()).count("match") == 1
                )
                for (seed, arm), net in models.items():
                    factors = log_paths(net, s, np.arange(16), "mps").cpu().numpy()
                    mass = factors.prod(1)
                    if abs(mass.sum() - 1) > 1e-4:
                        raise ValueError("incomplete physical distribution")
                    (valid,) = [k for k, v in labels.items() if v == "match"]
                    join = sum(
                        mass[k] for k, v in labels.items() if v in ("match", "guard")
                    )
                    result.append(
                        dict(
                            instance=i,
                            order=order,
                            seed=seed,
                            arm=arm,
                            join=float(join),
                            complete=float(mass[valid]),
                            first=float(factors[valid, 1]),
                            second=float(factors[valid, 2]),
                            guard_given_join=float(mass[valid] / join),
                        )
                    )
            finally:
                m.close_observer()
    write(a.out / "binding.json", result)


if __name__ == "__main__":
    torch.set_num_threads(1)
    audit(cli().parse_args())
