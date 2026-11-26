"""Compile only witnessed address paths into examples for the frozen physical tree."""

import gzip
import pickle

import numpy as np
import torch

from address_corpus import extract
from address_diagnosis import gates
from address_scores import tree, weight
from draft_multitarget import snapshots
from metal_scaling import CASES
from parallel_fit import TRAIN
from query_environment import offline_memory
from query_witnesses import arguments, groups


def compile_paths(s, group_sizes, gains, gate):
    bank = [np.zeros(99, np.float32)]
    cache = {}
    paths = []
    policies = []
    domains = s["domains"]
    gate_probs = {t: gates(d["queries"], d["gates"], gate) for t, d in domains.items()}
    for _, _, steps in s["tokens"]:
        path, policy = [], []
        for t, qi, leaf in steps:
            d = domains[t]
            keys = d["keys"]
            route = []
            if leaf >= 0 and len(keys) > 1:
                l, r, p, bits, mask, _ = tree(len(keys))
                for j, right in zip(p[leaf, mask[leaf]], bits[leaf, mask[leaf]]):
                    key = (t, qi, j)
                    if key not in cache:
                        kind = [float(t == -1), float(t != -1), 0.0]
                        cache[key] = len(bank)
                        bank.append(
                            np.asarray(
                                [*d["queries"][qi], *keys[l[j]], *keys[r[j]], *kind],
                                np.float32,
                            )
                        )
                    route.append(cache[key] if right else -cache[key])
            copy, project, switch, *_ = d["gates"][qi]
            c, g = gate_probs[t][qi]
            policy.append(
                (
                    c,
                    copy >= 0 and copy == leaf,
                    g if switch else -1.0,
                    project != -2,
                    project >= 0 and project == leaf,
                    1.0,
                    leaf >= 0,
                )
            )
            path.append(route)
        paths.append(path)
        policies.append(policy)
    n = len(paths)
    roles = max(map(len, paths))
    depth = max(1, max(len(route) for p in paths for route in p))
    ix = np.zeros((n, roles, depth), np.int32)
    meta = np.zeros((n, roles, 7), np.float32)
    meta[:, :, 2] = -1
    for i, p in enumerate(paths):
        for j, route in enumerate(p):
            ix[i, j, : len(route)] = route
        meta[i, : len(p)] = policies[i]
    return dict(
        features=np.asarray(bank),
        paths=ix,
        meta=meta,
        offsets=np.array([0, *np.cumsum(group_sizes)]),
        gains=np.asarray(gains),
    )


@torch.no_grad()
def run(a):
    gate = weight(a).to("mps").eval()
    for held, sources in [(False, TRAIN), (True, [(c, "teacher") for c in CASES])]:
        for case, source in sources:
            equiv = groups(a, case, source, held)
            for env in (False, True):
                dest = a.out / ("eval" if held else "train") / ("env" if env else "old")
                dest.mkdir(exist_ok=True, parents=True)

                def make(a, d):
                    return offline_memory(a, d, case, "B" if env else "A", source)

                for m, r, g in snapshots(a, case, source, make):
                    targets = []
                    sizes = []
                    for original in g:
                        variants = sorted(
                            equiv.get((r, original), ()), key=lambda c: c.refs
                        )
                        sizes.append(1 + len(variants))
                        targets.extend([original, *variants])
                    assert len(targets) == len(set(targets))
                    s = extract(m, targets, case, r)
                    data = compile_paths(s, sizes, list(g.values()), gate)
                    with gzip.open(
                        dest / f"{case}-{source}-{r:04d}.pkl.gz", "wb", compresslevel=1
                    ) as out:
                        pickle.dump(data, out, protocol=5)
                print(case, source, env, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(arguments().parse_args())
