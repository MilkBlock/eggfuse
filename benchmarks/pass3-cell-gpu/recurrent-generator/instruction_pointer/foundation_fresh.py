"""Capacity sensitivity when the existing read starts with independent gate rows."""

import torch

from foundation_fit import model, train
from foundation_world import data
from partner_index_worlds import args

if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    actor = model(a, 71, 32).actor
    ds = data(a, actor, "multi", True, 12)
    test = data(a, actor, "multi", False, 4)
    for width in (32, 128, 512):
        for seed in (71, 113):
            train(a, "multi", 12, width, seed, ds, test, True)
