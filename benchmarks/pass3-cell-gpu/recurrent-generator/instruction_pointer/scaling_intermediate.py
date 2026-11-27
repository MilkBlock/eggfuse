"""Validate nested training checkpoints after configuration selection, including the second seed at 10K."""

import argparse
import json
import time

from scaling_campaign import REPORT, SEEDS, Campaign, grid


def run(hours):
    c = Campaign(1, hours)
    if not c.state["locked"]:
        return
    selection = c.state["locked"]
    for name in ("initial", "factorized-random"):
        c.evaluate_frozen("outer", name)
    for name in ("decoder", "layer01", "layer03"):
        for seed in SEEDS:
            tag = f"{name}-s{seed}-t100000"
            if (c.disk / "fits" / (tag + ".pt")).exists():
                c.evaluate_frozen("outer", tag)
    for seed in SEEDS:
        name = f"{selection['name']}-s{seed}-t{selection['cap']}"
        for temperature in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            for unique in (0, 1):
                c.evaluate_frozen("selection", name, CELL_TEMP=temperature, CELL_UNIQUE=unique)
        for slots in (4, 12):
            c.evaluate_frozen("selection", name, CELL_SLOTS=slots)
    names = {g["name"] for g in grid()} | {"layer-lr-interaction"}
    for p in sorted((c.disk / "fits").glob("*-t*.json")):
        if time.time() > c.state["end"] - 600:
            return
        if p.stem in c.state["groups"] or (REPORT / "size-controls" / p.name).exists():
            continue
        g = json.loads(p.read_text())
        conf = g["config"]
        if (
            conf["name"] not in names
            or p.stem != f"{conf['name']}-s{g['seed']}-t{g['exposures']}"
        ):
            continue
        c.fit(conf, g["seed"], g["exposures"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=8)
    run(parser.parse_args().hours)
