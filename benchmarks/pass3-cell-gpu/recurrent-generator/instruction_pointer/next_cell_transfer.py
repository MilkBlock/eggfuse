"""Factorize the same joint probability on archived, native-witnessed evaluation roots."""

from collections import defaultdict
import numpy as np
import torch
from address_scores import weight
from discovery_score import write_csv
from discovery_states import cli
from next_cell_train import read
from query_fit import batch


@torch.no_grad()
def measure(a):
    rows = []
    for seed in (9633, 5003):
        for arm in ("initial", "ce24", "ce200", "ce200mixed"):
            net = weight(a).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / (arm + ".pt"), weights_only=True
                )
            )
            stats = defaultdict(list)
            for p in sorted((a.contract / "eval" / "env").glob("*.pkl.gz")):
                state = read(p)
                ids = np.flatnonzero(state["gains"] > 0)
                for i in range(0, len(ids), 128):
                    lp, prob = batch(net, state, ids[i : i + 128], "mps")
                    template = prob[:, 0].log()
                    joint = lp.logsumexp(1)
                    stats[p.name.split("-teacher-")[0]].append(
                        torch.stack((template, joint - template, joint), 1)
                        .cpu()
                        .numpy()
                    )
            for case, values in stats.items():
                v = np.concatenate(values)
                rows.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        case=case,
                        targets=len(v),
                        template_nll=float(-v[:, 0].mean()),
                        conditional_parents_nll=float(-v[:, 1].mean()),
                        full_nll=float(-v[:, 2].mean()),
                    )
                )
    write_csv(a.out / "transfer-nll.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    measure(cli().parse_args())
