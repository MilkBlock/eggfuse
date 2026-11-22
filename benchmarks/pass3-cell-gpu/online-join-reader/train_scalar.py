"""Fit small readouts on random signed integers; exhaust the deployment domain."""
import argparse
import itertools
import json
import operator
from pathlib import Path

import torch

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
       "+": operator.add, "-": operator.sub}


def train():
    torch.set_num_threads(1)
    rng = torch.Generator().manual_seed(2197)
    gates = {}
    for op, fn in OPS.items():
        x = torch.randint(-16, 17, (4096, 2), generator=rng).double()
        # Include adjacent and equal integers; uniform pairs alone underweight the boundary.
        x[:1024, 1] = (x[:1024, 0] + torch.randint(-1, 2, (1024,), generator=rng)).clamp(-16, 16)
        y = fn(x[:, 0], x[:, 1]).double()
        w = torch.nn.Parameter(torch.zeros(3, dtype=torch.double))
        opt = torch.optim.LBFGS([w], max_iter=150, line_search_fn="strong_wolfe",
                                tolerance_grad=1e-11, tolerance_change=1e-14)
        arithmetic = op in ("+", "-")
        def closure():
            opt.zero_grad()
            z = x @ w[:2] + w[2]
            loss = ((z-y).square().mean() if arithmetic else
                    torch.nn.functional.binary_cross_entropy_with_logits(z, y))
            loss.backward()
            return loss
        opt.step(closure)
        coeff = w.detach().tolist()
        for a,b in itertools.product(range(-16,17), repeat=2):
            score = coeff[0]*a + coeff[1]*b + coeff[2]
            if arithmetic:
                if abs(score-fn(a,b)) >= .25:
                    raise ValueError((op,a,b,score))
            elif (score>=0) != fn(a,b) or abs(score)<.1:
                raise ValueError((op,a,b,score))
        gates[op] = coeff
    return gates


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base",type=Path)
    parser.add_argument("out",type=Path)
    a=parser.parse_args()
    model=json.loads(a.base.read_bytes())
    model["scalars"]=train()
    a.out.write_text(json.dumps(model,indent=2)+"\n")
