"""Full-library recognition on reference events, conditional on the correct root rule."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
import torch

from deep_ripsat import measure
from event_addresses import Directory
from protocol_experiment import dump
from recursive_agent import Reader
from recursive_train import read
from ripsat_layout import capture, signatures
from ripsat_policy import CellScorer
from ripsat_replay import unpack
from side_boundary import address


@torch.no_grad()
def evaluate(root, out, name, size):
    donor = read(root / "sum/program.json")
    target = read(root / name / "program.json")
    catalog = read(out / "catalog.json")
    model_data = torch.load(out / "event-gnn.pt", weights_only=True)
    codes = model_data["codes"]
    width = codes.shape[1]
    model = CellScorer(width).eval()
    model.load_state_dict(model_data["model"])
    encoder = torch.nn.Linear(16, width)
    encoder.load_state_dict(model_data["encoder"])
    layouts = unpack(catalog["layouts"][:size])
    menus = defaultdict(list)
    available = set(signatures(target))
    for i, l in enumerate(layouts):
        if all(catalog["signatures"][rid] in available for rid, _, _ in l):
            menus[l[0][0]].append(i)
    rd = Reader(target, root, rename_seed=179)
    mem = Directory(rd, Counter())
    refs, mapped, roots, _ = capture(root / name, donor, 10, grow_consumers=True)
    runs = defaultdict(list)
    for j, q in enumerate(refs):
        runs[q["run"]].append((j, q))
    counts = Counter()
    union = set()
    # Deduplicate repeated requests for the same event and menu within one snapshot.
    for frame in map(
        json.loads, (root / name / "memory.jsonl").read_text().splitlines()
    ):
        rd.advance(frame)
        wm = dict(frame["rules"])
        selections = {}
        for j, q in runs[frame["run"]]:
            rid = mapped[q["rule"]]
            menu = menus.get(rid)
            if not menu:
                continue
            events = []
            for p in q["parents"]:
                tok, pc = address(p)
                a = rd.store.alias(tok), pc
                row = rd.store.visible[a]
                if row["version"] >= wm[q["rule"]]:
                    b = mem.bank(row["table"])
                    events.append((a, b.vec[b.positions[a]]))
            if not q["parents"]:
                events.append((None, np.zeros(16, np.float32)))
            for a, vec in events:
                key = (a, rid)
                if key not in selections:
                    x = encoder(torch.from_numpy(vec))
                    scores = model(x.expand(len(menu), -1), codes[menu])[:, 1]
                    best = int(scores.argmax())
                    selections[key] = menu[best] if scores[best] > 0 else None
                    counts["scores"] += len(menu)
                uid = selections[key]
                if uid is None:
                    continue
                counts["selected_event_root_pairs"] += 1
                for _, ready, first, tokens in roots.get(j, {}).get(layouts[uid], ()):
                    if ready and first:
                        union.update(tokens)
                        counts["matched_instances_with_repetition"] += 1
    return dict(
        compatible_templates=sum(map(len, menus.values())),
        commits=len(refs),
        selected_ready_distinct_steps=len(union),
        **measure(roots, set(layouts)),
        **counts,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    dump(
        a.out / "recognition.json",
        {
            size: {
                n: evaluate(a.root, a.out, n, size)
                for n in ("fact", "loopfact", "sum-divisors")
            }
            for size in (4096, 10000)
        },
    )
