"""Compare the training gradient with finite differences after recalibrating both group thresholds."""
import torch
from train import marginal_derivative


def reward(z, groups, n, y, quotas):
    value = 0.
    for g, quota in enumerate(quotas):
        local = groups == g
        lo, hi = -40., 40.
        for _ in range(60):
            mid = (lo + hi) / 2
            if torch.sum(n[local] * torch.sigmoid(z[local] - mid)) > quota:
                lo = mid
            else:
                hi = mid
        value += torch.sum(y[local] * torch.sigmoid(z[local] - (lo + hi) / 2))
    return value / quotas.sum()


if __name__ == "__main__":
    torch.set_default_dtype(torch.float64)
    z = torch.tensor([.3, -.7, 2., -.3, 1.1])
    g = torch.tensor([0, 0, 0, 1, 1])
    n, y, k = torch.tensor([3., 5., 1., 4., 3.]), torch.tensor([3., 1., 0., 1., 3.]), torch.tensor([4., 2.])
    gradient = marginal_derivative(z, g, n, y, k)
    for i in range(len(z)):
        delta = torch.zeros_like(z)
        delta[i] = 1e-5
        measured = (reward(z + delta, g, n, y, k) - reward(z - delta, g, n, y, k)) / (2 * delta[i])
        assert abs(measured - gradient[i]) < 1e-8
    print("Quota gradient agrees with independent central differences for each logit.")
