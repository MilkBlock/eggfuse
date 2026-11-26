"""Paired held-state probes and native rollouts on unseen program signatures."""

import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np
import torch

from address_scores import weight
from credit_scale_held import trial
from discovery_states import cli, read
from fine_fit import load_data, path_factors
from recursive_coverage import Target, snapshot
from transition_fit import prepare


@torch.no_grad()
def evaluate(a):
    gate = weight(a).to("mps").eval()
    ckpt = a.out / "weights"
    with (a.out / ("held-" + a.label + ".jsonl")).open("w") as out:
        for idx in range(256, 264):
            bank = a.previous / "programs" / f"{idx:04}"
            base = SimpleNamespace(**(vars(a) | {"out": a.held}))
            data, rec, pairs, edits, edges = load_data(base, idx, bank)
            forced = list(pairs)
            for k, bad, good, slot in edits:
                forced.extend([(k, k, bad), (k, k, good)])
            for (k, c), (j, d) in edges:
                forced.extend([(k, k, c), (j, j, d)])
            keys = list(rec)
            enc = prepare(
                a, bank, data, rec, keys, forced, np.random.default_rng(idx), gate
            )
            with TemporaryDirectory() as td:
                file = Path(td) / "snap"
                ref = Target(
                    read(bank / "program.json"),
                    snapshot(a.data, bank, "reference", "-", None, file)[0],
                )
                initial = ref.match(
                    snapshot(a.data, bank, "reference", "-", 0, file)[0]
                )
                for seed in (9633, 5003):
                    for arm in a.arms if seed == 9633 else reversed(a.arms):
                        v = trial(a, bank, arm, seed, initial, ref)
                        if arm != "factored":
                            net = weight(a).to("mps").eval()
                            net.load_state_dict(
                                torch.load(
                                    ckpt / str(seed) / (arm + ".pt"), weights_only=True
                                )
                            )
                            paths = {
                                k: path_factors(net, r).cpu().numpy()
                                for k, r in enc.items()
                                if r
                            }

                            def fields(k, c, paths=paths, enc=enc):
                                return paths[k][enc[k][1][c]]

                            m = Counter()
                            for x, y, c in pairs:
                                m["paired_total"] += 1
                                m["paired_right"] += int(
                                    fields(x, c).prod() > fields(y, c).prod()
                                )
                                m["prob_unfinished"] += float(fields(x, c).prod())
                                m["prob_done"] += float(fields(y, c).prod())
                            for k, b, d, j in edits:
                                m["substitution_total"] += 1
                                m["substitution_right"] += int(
                                    fields(k, d)[1 + j] > fields(k, b)[1 + j]
                                )
                            for k, r in enc.items():
                                if r:
                                    for c in r[1]:
                                        if c in rec[k]["positive"] and c.refs:
                                            m["known_valid_tuple_count"] += 1
                                            m["conditional_parent_prob_sum"] += float(
                                                fields(k, c)[1:].prod()
                                            )
                            for (x, c), (y, d) in edges:
                                m["observed_path_count"] += 1
                                m["upstream_prob_sum"] += float(fields(x, c).prod())
                            v.update(m)
                        out.write(json.dumps(v) + "\n")
                        out.flush()
            print("held", idx, flush=True)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--arms", nargs="+", required=True)
    p.add_argument("--held", type=Path, required=True)
    p.add_argument("--label", default="fine")
    torch.set_num_threads(1)
    evaluate(p.parse_args())
