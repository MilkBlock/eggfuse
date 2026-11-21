"""Check gradients and deployed count predictions independently of the optimizer."""
import hashlib
import json
import math

import torch
from train import CAP, DONORS, DTYPE, HERE, INPUT, QUANTILES, counts, load, objective, predict


def scalar_count(name, weights, row, offered):
    # Use sequential scalar arithmetic and Rust's nonnegative half-up round.
    z = sum(w * value for w, value in zip(weights, row))
    if name == "fraction":
        fraction = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
        raw = offered * fraction
    else:
        raw = math.expm1(max(0, min(z, math.log1p(CAP))))
    return min(offered, CAP, math.floor(raw + 0.5))


def check():
    policy = json.loads((HERE / "policy.json").read_bytes())
    assert policy["input_sha256"] == hashlib.sha256(INPUT.read_bytes()).hexdigest()
    assert policy["donors"] == list(DONORS) and policy["cap"] == CAP
    assert set(policy["models"]) == {*QUANTILES, "fraction"}
    data = load(INPUT)
    all_data = tuple(torch.cat(parts) for parts in zip(*data.values()))
    # Exact finite differences away from the pinball and count-clip kinks.
    x = torch.tensor([[1, .2, .7, .1, 0, .3, .8, math.log1p(7)],
                      [1, .7, .4, .2, .3, .1, .6, math.log1p(12)],
                      [1, .1, .6, .7, .1, .4, .1, 0]], dtype=DTYPE)
    fixture = (x, *(torch.tensor(v, dtype=DTYPE) for v in ([7,12,0], [0,5,0], [3,1,4])))
    for name in policy["models"]:
        probe = torch.tensor([.6,.1,-.2,.05,.12,-.01,.14,.04], dtype=DTYPE, requires_grad=True)
        assert torch.autograd.gradcheck(lambda w: objective(name, w, fixture), (probe,))
        params = policy["models"][name]
        assert len(params) == 8 and all(math.isfinite(v) for v in params)
        w = torch.tensor(params, dtype=DTYPE)
        assert policy["fit"][name]["fitted_loss"] < policy["fit"][name]["initial_loss"]
        assert abs(float(objective(name,w,all_data)) - policy["fit"][name]["fitted_loss"]) < 1e-12
        for donor, batch in (*data.items(), ("total", all_data)):
            assert counts(name, w, batch) == policy["training_counts"][name][donor]
        xs, ns = all_data[:2]
        measured = (predict(name,w,xs,ns)+0.5).floor().tolist()
        assert measured == [scalar_count(name,params,row,int(n)) for row,n in zip(xs.tolist(),ns.tolist())]
        # Held-out count extremes, including cap and half-up rounding.
        assert scalar_count(name,[1000.]+[0.]*7,[1.]+[0.]*7,10*CAP) == CAP
        assert scalar_count(name,[-1000.]+[0.]*7,[1.]+[0.]*7,10*CAP) == 0
        assert scalar_count(name,params,[1.]+[0.]*7,0) == 0
    assert scalar_count("fraction",[0.]*8,[1.]+[0.]*7,1) == 1
    print("Three gradient checks passed. All frozen donor histogram predictions and totals match scalar deployment.")

if __name__ == "__main__":
    torch.set_num_threads(1)
    check()
