"""Execute held dynamic programs and check exact same-Token state preferences offline."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from address_scores import weight
from credit_scale_held import trial
from discovery_states import cli, read
from recursive_coverage import Target, snapshot
from transition_credit import contrasts, reduce_data, schema
from transition_fit import load_program, prepare, probs


@torch.no_grad()
def main(a):
    gate = weight(a).to("mps").eval()
    records = []
    for idx in range(256, 264):
        d = a.previous / "programs" / f"{idx:04d}"
        data = load_program(a.out / "held", idx)
        assert set(data) == {1, 2}
        limits = {b: (10**9, 10**9) for b in data}
        rec = reduce_data(data, schema(read(d / "program.json")), limits, idx)
        pairs = contrasts(rec)
        enc = prepare(a, d, data, rec, [], pairs, np.random.default_rng(idx), gate)
        with TemporaryDirectory() as td:
            tmp = Path(td) / "state"
            target = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, tmp)[0],
            )
            initial = target.match(snapshot(a.data, d, "reference", "-", 0, tmp)[0])
            for seed in (9633, 5003):
                for arm in a.arms:
                    r = trial(a, d, arm, seed, initial, target)
                    if arm != "factored":
                        gate.load_state_dict(
                            torch.load(
                                a.out / "weights" / str(seed) / (arm + ".pt"),
                                weights_only=True,
                            )
                        )
                        ps = {
                            key: probs(gate, v).cpu().tolist()
                            for key, v in enc.items()
                            if v is not None
                        }
                        diffs = [
                            np.log(max(1e-30, ps[x][enc[x][1][c]]))
                            - np.log(max(1e-30, ps[y][enc[y][1][c]]))
                            for x, y, c in pairs
                        ]
                        r.update(
                            pairs=len(pairs),
                            right=sum(bool(v > 0) for v in diffs),
                            log_ratio_sum=sum(diffs),
                        )
                        # Gate features must always be encoded by the original frozen gates.
                        gate.load_state_dict(weight(a).state_dict())
                    records.append(r)
        print("held", idx, flush=True)
    (a.out / ("held-" + a.label + ".jsonl")).write_text(
        "".join(json.dumps(r) + "\n" for r in records)
    )


if __name__ == "__main__":
    p = cli()
    p.add_argument("--arms", nargs="+", required=True)
    p.add_argument("--label", required=True)
    torch.set_num_threads(1)
    main(p.parse_args())
