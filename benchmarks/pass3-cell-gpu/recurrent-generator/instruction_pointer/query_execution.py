"""Sample live GPU pages and verify signed requests on the native independent schedule."""

import torch

from address_runtime import frozen, native
from metal_scaling import CASES
from query_environment import offline_memory, online_memory, setup
from query_witnesses import arguments

if __name__ == "__main__":
    p = arguments()
    p.add_argument("mode", choices=("native", "frozen"))
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--arms", nargs="+", default=list("ABCD"))
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--cap", type=int, default=16)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--seconds", type=int, default=240)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.mode == "frozen":
        frozen(a, setup, offline_memory)
    else:
        native(a, setup, online_memory)
