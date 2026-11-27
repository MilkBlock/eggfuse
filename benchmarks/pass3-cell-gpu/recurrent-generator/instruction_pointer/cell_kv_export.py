"""Export audit, costs, paired native results and frozen checkpoint digests."""

import csv
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

import torch
from cell_kv_study import names, digest
from cell_kv_world import World
from first_parent import records
from partner_index_worlds import args
from rule_read import load_actor


def export(a):
    out = Path(os.environ.get("RESULTS_DIR", "run-recall/cell-kv"))
    out.mkdir(exist_ok=True, parents=True)
    ctrl = Path(os.environ.get("KV_OWNER_OUT", a.out.parent / "cell-kv-balanced"))
    raw = json.loads((a.out / "native.json").read_text()) + json.loads(
        (a.out / "untyped.json").read_text()
    )
    for r in json.loads((ctrl / "readout-control.json").read_text()):
        r["arm"] += "-owner-readout"
        raw.append(r)
    (out / "native.json").write_text(json.dumps(raw, separators=(",", ":")) + "\n")
    grouped = defaultdict(list)
    paired = defaultdict(list)
    for r in raw:
        grouped[r["arm"], r["joint"], r["updates"]].append(r)
        paired[
            r["case"], r["arm"], r["joint"], r["updates"], r["draw"], r["seed"]
        ].append(r)
    for group in paired.values():
        assert len(group) == 2
        assert (
            group[0]["facts"] == group[1]["facts"]
            and group[0]["graph"] == group[1]["graph"]
        )
        assert group[0]["stats"] == group[1]["stats"]
    rows = []
    for (arm, joint, step), rs in sorted(grouped.items()):
        draws = [r for r in rs if not r["block"]]
        ranges = [
            abs(g[0]["wall"] - g[1]["wall"]) / mean(r["wall"] for r in g)
            for key, g in paired.items()
            if key[1:4] == (arm, joint, step)
        ]
        rows.append(
            dict(
                arm=arm,
                joint=int(joint),
                updates=step,
                draws=len(draws),
                clocks=len(rs),
                **{
                    k: mean(r[k] for r in rs)
                    for k in ("coverage", "covered", "ops", "ept", "eps", "wall")
                },
                **{
                    k: sum(r["stats"].get(k, 0) for r in draws)
                    for k in (
                        "paid",
                        "neural_tokens",
                        "higher_selected",
                        "higher_opened",
                        "higher_completed",
                        "accepted_consumer_of_higher",
                    )
                },
                mean_pending=mean(r["pending"] for r in rs),
                matched_reference=sum(r["reference_graph"] for r in draws),
                median_relative_clock_range=median(ranges),
            )
        )
    records(out / "summary.csv", rows)
    training = []
    for f in sorted((a.out / "weights").glob("*.csv")):
        with f.open() as stream:
            training.extend(csv.DictReader(stream))
    records(out / "training.csv", training)
    for key in ("counter", "size", "owner", "oneshot", "legacy", "fit"):
        shutil.copyfile(a.out / f"{key}.csv", out / f"{key}.csv")
    model = load_actor(a.actor, True)
    manifests = []
    fill = {}
    for split in ("train", "held"):
        fill[split] = set()
        for name, *_ in names(split):
            d = a.out / "worlds" / name
            source = (d / "world.egg").read_text()
            for x, y in re.findall(r"^\(Seed (\d+) (\d+)\)$", source, re.M):
                fill[split].update((x, y))
            w = World(d, model)
            manifests.append(
                dict(
                    split=split,
                    name=name,
                    recipe_sha=hashlib.sha256(
                        (d / "program.json").read_bytes()
                    ).hexdigest(),
                    higher_steps=len(w.layouts[-1]),
                    signatures=digest(w),
                    reference_graph=json.loads((d / "capture.json").read_text())[
                        "state_sha"
                    ],
                )
            )
    assert not fill["train"] & fill["held"]
    sigs = {
        split: {s for m in manifests if m["split"] == split for s in m["signatures"]}
        for split in fill
    }
    assert not sigs["train"] & sigs["held"]
    data = torch.load(a.out / "training.pt", weights_only=False)
    entries = sum(map(len, data.values()))
    unique = set()
    verified = set()
    for name, rows in data.items():
        for state, targets in rows:
            k = name, json.dumps(state, separators=(",", ":"), sort_keys=True)
            unique.add(k)
            verified.update((k, t, refs) for t, refs in targets)
    result = dict(
        programs=manifests,
        source_states=entries,
        distinct_states=len(unique),
        distinct_state_target=len(verified),
        unique_input_values={s: len(xs) for s, xs in fill.items()},
        file_sha256={
            f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted((a.out / "weights").glob("*.pt"))
        },
        training_sha256=hashlib.sha256(
            (a.out / "training.pt").read_bytes()
        ).hexdigest(),
    )
    (out / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    export(args())
