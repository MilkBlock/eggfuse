"""Full two-step rollout, followed by independent source audit and matched MPS timings."""

import argparse
import itertools
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np
import torch

from data import dataset, audit
from fit import device
from learning import ARMS, System
from study import Study, SEEDS, VALUE_CLASSES, MANIFEST, digest


def transfer(d, idx, dev):
    return tuple(
        torch.as_tensor(d[k][idx], device=dev, dtype=torch.int32) for k in ("a", "b", "requests")
    )


def discrete(stages):
    return [
        {k: s[k].detach().cpu().numpy() for k in ("active", "pointers", "rows")} for s in stages
    ]


def select(d, idx):
    return {k: (v[idx] if isinstance(v, np.ndarray) else v) for k, v in d.items()}


def initialized(root, study, dev, arms):
    models = {}
    fits = {}
    for seed in SEEDS:
        for arm in arms:
            name = f"{arm}-{seed}"
            folder = root / name
            info = json.loads((folder / "fit.json").read_text())
            if (
                info["manifest_sha256"] != digest(MANIFEST)
                or digest(folder / "model.pt") != info["weight_sha256"]
            ):
                raise ValueError(f"checkpoint or partition changed: {name}")
            m = System(study.schema, len(study.rules), arm, study.columns, VALUE_CLASSES, seed)
            m.load_state_dict(
                torch.load(folder / "model.pt", weights_only=True, map_location="cpu")
            )
            fits[name] = info
            models[name] = m.to(dev).eval()
        group = [fits[f"{a}-{seed}"]["initial"] for a in arms]
        for key in ("common", "head", "aux"):
            if len({g[key] for g in group}) != 1:
                raise AssertionError(key)
        encoded = [fits[f"{a}-{seed}"]["initial"]["encoder"] for a in arms if not a.endswith("_id")]
        if len(set(encoded)) != 1:
            raise AssertionError("encoder initialization differs")
    return models, fits


def audit_compact(d, stages):
    full = audit(d, *stages)
    per = full["run2"]["per_graph"]
    if d["split"] == "collision":
        twins = sum(per[i]["complete"] and per[i + 1]["complete"] for i in range(0, len(per), 2))
    else:
        twins = None
    consistent = [r for r in per if r["nonempty"] and r["residual_reads_consistent"]]
    metrics = ("complete", "wrong_live_parent", "duplicates", "missing", "illegal", "obligations")
    consistent_counts = {k: sum(row[k] for row in consistent) for k in metrics}
    return dict(
        consistent=dict(graphs=len(consistent), **consistent_counts),
        run1={k: v for k, v in full["run1"].items() if k != "per_graph"},
        run2={k: v for k, v in full["run2"].items() if k != "per_graph"},
        complete_by_graph=[int(r["complete"]) for r in per],
        nonempty_by_graph=[int(r["nonempty"]) for r in per],
        complete_twin_pairs=twins,
    )


@torch.inference_mode()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--capacity", action="store_true")
    a = p.parse_args()
    dev = device()
    st = Study()
    arms = ("private_roles", "shared_roles", "wide_roles") if a.capacity else ARMS
    models, fits = initialized(a.root, st, dev, arms)
    all_reports = {}
    timings = {}
    trace_dir = a.root / ("capacity-traces" if a.capacity else "traces")
    trace_dir.mkdir(exist_ok=True)
    branches = list(models)
    for ti, t in enumerate(st.templates):
        tid = t["id"]
        g = st.schema.pack(t, dev)
        static = st.static(t)
        cached = {name: model.encoder(g) for name, model in models.items()}
        torch.mps.synchronize()
        for split in ("iid", "collision"):
            d = dataset(split, t)
            panels = {}
            for name, m in models.items():
                stages, token = m.infer(transfer(d, slice(None), dev), static, cached[name])
                torch.mps.synchronize()
                out = discrete(stages)
                payload = token.detach().cpu().numpy()
                assert np.isfinite(payload).all()
                np.testing.assert_array_equal(
                    payload[
                        ...,
                        m.decoder.payload_offset : m.decoder.payload_offset
                        + out[0]["rows"].shape[-1],
                    ],
                    out[0]["rows"],
                )
                if split == "collision":
                    # The second source event changes; the common producer prefix must be invariant.
                    np.testing.assert_array_equal(payload[::2], payload[1::2])
                if t["split"] == "heldout" and split == "collision":
                    np.savez_compressed(
                        trace_dir / f"{tid}-{name}.npz",
                        token=payload,
                        **{f"{i}_{k}": v for i, s in enumerate(out) for k, v in s.items()},
                    )
                panels[name] = audit_compact(d, out)
            all_reports[f"{tid}/{split}"] = panels
        if t["split"] != "heldout":
            continue
        d = dataset("collision", t)
        idx = np.random.default_rng(77213 + ti).choice(len(d["a"]), 16, replace=False)
        buckets = {}
        timings[tid] = {}
        for cold in (False, True):
            kind = "cold" if cold else "cached"
            for name, m in models.items():
                for i in idx[:2]:
                    cond = m.encoder(st.schema.pack(t, dev)) if cold else cached[name]
                    m.infer(transfer(d, slice(i, i + 1), dev), static, cond)
                    torch.mps.synchronize()
            samples = {name: [] for name in branches}
            kept = {name: [] for name in branches}
            for j, i in enumerate(idx):
                offset = (j + ti) % len(branches)
                for name in branches[offset:] + branches[:offset]:
                    m = models[name]
                    start = time.perf_counter_ns()
                    dynamic = transfer(d, slice(i, i + 1), dev)
                    cond = m.encoder(st.schema.pack(t, dev)) if cold else cached[name]
                    stages, token = m.infer(dynamic, static, cond)
                    torch.mps.synchronize()
                    samples[name].append((time.perf_counter_ns() - start) / 1e6)
                    kept[name].append((stages, token))
            timed = {}
            for name in branches:
                outs = [discrete(s) for s, _ in kept[name]]
                pred = [
                    {k: np.concatenate([row[i][k] for row in outs]) for k in outs[0][i]}
                    for i in (0, 1)
                ]
                r = audit(select(d, idx), *pred)["run2"]
                for _, token in kept[name]:
                    assert np.isfinite(token.detach().cpu().numpy()).all()
                timed[name] = dict(
                    samples_ms=samples[name],
                    median_ms=statistics.median(samples[name]),
                    complete=r["nonempty_complete_graphs"],
                    nonempty=r["nonempty_graphs"],
                    indices=idx.tolist(),
                    correct_nonempty_per_second=r["nonempty_complete_graphs"]
                    * 1000
                    / sum(samples[name]),
                )
                if not cold:
                    buckets[name] = pred
                else:
                    for stage1, stage2 in zip(buckets[name], pred):
                        for k in stage1:
                            np.testing.assert_array_equal(stage1[k], stage2[k])
            timings[tid][kind] = timed
        print(
            "held-out",
            tid,
            [
                (name, all_reports[f"{tid}/collision"][name]["run2"]["nonempty_complete_graphs"])
                for name in branches
            ],
            flush=True,
        )
    summary = dict(
        scope="single-row ordered two-leaf Bake interface; collision and IID clouds are synthetic graph instances",
        manifest_sha256=digest(MANIFEST),
        fits=fits,
        panels=all_reports,
        timings=timings,
    )
    (a.root / ("capacity.json" if a.capacity else "results.json")).write_text(
        json.dumps(summary, separators=(",", ":")) + "\n"
    )


if __name__ == "__main__":
    main()
