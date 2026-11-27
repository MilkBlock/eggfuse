import torch

from multirule_corpus import collect
from partner_index_worlds import args, frozen
from recursive_train import folder

if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    m = frozen(a, a.seeds[0])
    for case in ("fact", "loopfact", "sum-divisors"):
        out = a.out / "corpus" / ("rollout-" + case)
        out.mkdir(parents=True, exist_ok=True)
        collect(
            a,
            m,
            "rollout-" + case,
            folder(a.data, case),
            a.out / case / "audit-0/accepted.json",
            out,
        )
