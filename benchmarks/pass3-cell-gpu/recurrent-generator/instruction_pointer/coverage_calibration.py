"""Measure finite-bank partition error against fresh Metal slots on training states."""

from collections import Counter

import numpy as np
import torch

from address_scores import weight
from coverage_eval import choices
from coverage_fit import ARMS, expected_distinct, probability
from discovery_score import write_csv
from discovery_states import cli
from draft_multitarget import snapshots
from parallel_fit import TRAIN
from query_environment import conditioned
from query_fit import read


@torch.no_grad()
def measure(a):
    rows = []
    networks = {arm: weight(a).to("mps").eval() for arm in ARMS}
    for arm, net in networks.items():
        net.load_state_dict(
            torch.load(a.out / "weights" / "9633" / f"{arm}.pt", weights_only=True)
        )
    for case, src in TRAIN:

        def build(args, d, case=case, src=src):
            m = conditioned(a, d, a.contract / f"state-{case}-{src}.jsonl")
            m.pages = {arm: choices(a, m, arm, 512, 9633)[2] for arm in ARMS}

            def publish(frame):
                for page in m.pages.values():
                    page.publication(frame)

            m.on_page_publication = publish
            return m

        for j, (m, r, _) in enumerate(snapshots(a, case, src, build)):
            s = read(a.out / "examples" / f"{case}-{src}-{r:04}.pkl.gz")
            if j % 5 and not s["exact"]:
                continue
            for arm, page in m.pages.items():
                q = probability(networks[arm], s).prod(1).cpu().numpy()
                n = len(s["signature"])
                z = q[:n].sum() + q[n:] @ s["importance"]
                rng = np.random.default_rng(927103 + r)
                count = sum(
                    len(page.sample(m, (), 1, rng, Counter())) for _ in range(4)
                )
                mass = np.bincount(
                    s["signature"], weights=q[:n], minlength=len(s["gains"])
                )
                prob = torch.from_numpy(np.clip(mass / max(z, 1e-30), 0, 1))
                rows.append(
                    {
                        "case": case,
                        "source": src,
                        "run": r,
                        "arm": arm,
                        "exact": s["exact"],
                        "z_est": float(z),
                        "z_observed": count / 2048,
                        "generated": count,
                        "attempts": 2048,
                        "expected_256": float(
                            expected_distinct(prob[s["gains"] > 0], 256).sum()
                        ),
                    }
                )
    write_csv(a.out / "calibration.csv", rows)


if __name__ == "__main__":
    a = cli().parse_args()
    torch.set_num_threads(1)
    measure(a)
    torch.mps.synchronize()
