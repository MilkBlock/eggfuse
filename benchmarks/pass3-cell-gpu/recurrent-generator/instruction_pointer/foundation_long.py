"""Additional exposure and state-count axes from the same initialization and curriculum."""

import torch

from foundation_fit import STEPS, model, train
from foundation_world import data
from partner_index_worlds import args

if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    actor = model(a, 71, 32).actor
    test = data(a, actor, "multi", False, 4)
    train_states = data(a, actor, "multi", True, 48)
    for n, steps in ((48, STEPS), (24, STEPS + (1024, 2048))):
        for width in (32, 512):
            for seed in (71, 113):
                train(
                    a,
                    "multi",
                    n,
                    width,
                    seed,
                    train_states[:n],
                    test,
                    checkpoints=steps,
                )
