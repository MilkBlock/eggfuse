"""Shadow activation recall at oracle root boundaries. No teacher inputs in live runs."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
import torch
from generation_higher import BAKE, Layouts, Recognizer
from higher_replacement import split
from recursive_train import folder, read
from protocol_experiment import dump
from ripsat_replay import unpack
from template_routing import records, Dispatch


@torch.no_grad()
def run(root, out, case, donor):
    units = unpack(read(BAKE / "catalog.json"))
    group = [split(u) for u in units]
    cat = Layouts(read(folder(root, case) / "program.json"))
    rid_by_id = {cat.original[i]: r for r, menu in cat.by.items() for i in menu}
    rows = defaultdict(list)
    for x, menu, good in records(root, case, donor, False):
        rows[rid_by_id[menu[0]]].append((x, good))
    dense = Recognizer(cat.codes.shape[1]).eval()
    dense.load_state_dict(
        torch.load(Path("run-recall/structural-reach/higher.pt"), weights_only=True)
    )
    report = []
    for fraction in (0.125, 0.5, 1.0):
        for arm in ("full", "direct", "sparse", "tree"):
            d = Dispatch(cat, out, arm, fraction, dense)
            tally = Counter()
            den = Counter()
            got = Counter()
            seconds = 0.0
            for r, examples in rows.items():
                eligible = {cat.original[i] for i in d.menus.get(r, ())}
                for start in range(0, len(examples), 512):
                    subset = examples[start : start + 512]
                    if eligible:
                        x = torch.stack([x for x, _ in subset])
                        tick = perf_counter()
                        ids = d.select(r, x, tally).tolist()
                        seconds += perf_counter() - tick
                    else:
                        ids = [-1] * len(subset)
                    for uid, (_, good) in zip(ids, subset):
                        y = good & eligible
                        pred = -1 if uid < 0 else cat.original[uid]
                        tally["all_root_states"] += 1
                        tally["selected"] += int(pred >= 0)
                        tally["any_catalog_positive"] += bool(good)
                        if y:
                            for label in (
                                "any",
                                "fit",
                                "layout",
                                "pair",
                                "unseen_long",
                            ):
                                if label == "any":
                                    valid = y
                                elif label == "unseen_long":
                                    valid = {
                                        k
                                        for k in y
                                        if group[k] != "fit" and len(units[k]) > 2
                                    }
                                else:
                                    valid = {k for k in y if group[k] == label}
                                if valid:
                                    den[label] += 1
                                    got[label] += pred in valid
            report.append(
                dict(
                    fraction=fraction,
                    arm=arm,
                    layouts=sum(map(len, d.menus.values())),
                    seconds=seconds,
                    setup_seconds=d.setup,
                    counts=tally,
                    positives=den,
                    hits=got,
                )
            )
    dump(out / f"router-recall-{case}.json", report)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("donor", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        run(a.root, a.out, case, read(a.donor / "program.json"))
