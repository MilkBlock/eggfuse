"""Check baseline complete-target likelihood against the previous production path compiler."""

import numpy as np
import torch
from address_scores import weight
from binding_model import Decoder, parser, tensor, collate, read_packet
from completion_context import read, write
from coverage_examples import pack
from discrete_cells import from_q
from query_environment import conditioned
from query_fit import log_paths
import json


@torch.no_grad()
def parity(a):
    net = Decoder(a, "B").to("mps").eval()
    net.load_state_dict(torch.load(a.out / "weights/9633/B.pt", weights_only=True))
    gate = weight(a).to("mps")
    rows = []
    for variant in ["eq10", "two", "chain", "four", "guard", "merge"]:
        d = next((a.out / "worlds/test").glob("0016-" + variant + "-*"))
        z = read_packet(d / "binding.pkl")
        m = conditioned(a, d, d / "query.jsonl")
        try:
            for line in (d / "public.jsonl").read_text().splitlines():
                frame = json.loads(line)
                m.update(frame)
                if frame["run"] == 2:
                    break
            qs = read(d / "ok.json")["gold"]
            cells = list(map(from_q, qs))
            compiled = pack(m, cells, gate, "parity", 2)
            expected = log_paths(net.scorer, compiled, np.arange(len(qs)), "mps")[:, 1:]
            refs = [
                [z["addrs"][j].index(ref) for j, ref in enumerate(c.refs)]
                for c in cells
            ]
            y = tensor(np.array([refs]))
            ps, _ = net(collate([z]), y)
            actual = torch.stack(
                [
                    p.gather(-1, y[:, :, j, None]).exp()[0, :, 0]
                    for j, p in enumerate(ps)
                ],
                1,
            )
            torch.testing.assert_close(actual, expected, atol=2e-6, rtol=2e-5)
            rows.append(
                dict(
                    layout=variant,
                    goals=len(qs),
                    max_error=float((actual - expected).abs().max()),
                )
            )
        finally:
            m.close_observer()
    write(a.out / "parity.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    parity(parser().parse_args())
