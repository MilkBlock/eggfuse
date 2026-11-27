"""Match the response-visible CE training exposure, changing only the support."""

import torch

from constructible_study import directory
from feedback_train import train
from partner_index_worlds import args

if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    for seed in (71, 113):
        train(a, "visible", seed, condition_on_types=True, output=directory(a))
