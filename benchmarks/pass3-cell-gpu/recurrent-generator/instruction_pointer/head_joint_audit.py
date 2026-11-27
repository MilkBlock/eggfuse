"""Offline mathematical diagnostics. Never imported by the online generator."""

import numpy as np


def overlaps(query, partner):
    """Coordinate-list head products only where two neural supports intersect."""
    qi, qv = (x[0].cpu().numpy() for x in query)
    vi, vv = (x[0].cpu().numpy() for x in partner)
    n = vi.shape[1]
    codes, weights, heads = [], [], []
    for h in range(4):
        q = qi[h].ravel()
        v = vi[h].ravel()
        order = v.argsort(kind="stable")
        left = np.searchsorted(v[order], q)
        count = np.searchsorted(v[order], q, side="right") - left
        idx = np.repeat(np.arange(len(q)), count)
        peer = order[
            np.arange(len(idx)) + np.repeat(left - (count.cumsum() - count), count)
        ]
        weight = qv[h].ravel()[idx] * vv[h].ravel()[peer]
        ok = weight > 0
        codes.append((idx[ok] // 2) * n + peer[ok] // 2)
        weights.append(weight[ok])
        heads.append(np.full(ok.sum(), h, np.int8))
    pairs, back = np.unique(np.concatenate(codes), return_inverse=True)
    k = np.zeros((len(pairs), 4), np.float64)
    np.add.at(k, (back, np.concatenate(heads)), np.concatenate(weights))
    return pairs // n, k


def score(k, strength):
    return strength * (np.log(k + 1e-5) - np.log1p(k)).sum(axis=-1)


def diagnose(query, partner, prior, strength, root, c_mass):
    n = len(prior)
    owners, k = overlaps(query, partner)
    base = float(np.exp(score(np.zeros(4), strength)))
    joint = np.exp(score(k, strength))
    # B: original nonlinear score on one partner, then marginalize.
    b = n * base + np.bincount(owners, weights=joint - base, minlength=n)
    c = np.bincount(owners, weights=k.prod(1), minlength=n)
    # D: best individual partner, the optimistic dense joint-score diagnostic.
    d = np.full(n, base)
    np.maximum.at(d, owners, joint)
    seen = np.zeros((n, 4), bool)
    np.logical_or.at(seen, owners, k > 0)
    rtn = {
        "distributed_only": int((seen.all(1) & (c == 0)).sum()),
        "overlapping_pairs": len(owners),
        "positive_joint_roots": int((c > 0).sum()),
        "max_mass_error": float(np.abs(c - c_mass).max()),
    }
    for name, weight in (("B", b), ("C", c + 1e-12), ("D", d)):
        p = weight * np.exp(prior - prior.max())
        rtn[name + "_rank"] = int((p > p[root]).sum() + 1)
        rtn[name + "_prob"] = float(p[root] / p.sum())
    # Direct dense partner vector only for the true root and strongest D rival.
    # Includes partners sharing zero neural coordinates. No Cartesian tensor.
    qi, qv = (x[0].cpu().numpy() for x in query)
    vi, vv = (x[0].cpu().numpy() for x in partner)
    rival = d.copy()
    rival[root] = -1
    for r in {root, int(rival.argmax())}:
        h = (
            (
                (qi[:, r, None, :, None] == vi[:, :, None, :])
                * qv[:, r, None, :, None]
                * vv[:, :, None, :]
            )
            .sum((2, 3))
            .T
        )
        exact = np.exp(score(h.astype(np.float64), strength))
        np.testing.assert_allclose(
            [b[r], d[r]], [exact.sum(), exact.max()], rtol=3e-4, atol=1e-110
        )
    return rtn
