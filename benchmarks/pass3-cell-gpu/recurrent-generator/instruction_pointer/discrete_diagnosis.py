"""Offline only: isolate number of edits, static template addressing and named parent addressing."""

from collections import Counter

import numpy as np
import torch

from discrete_editor import sampler
from discrete_study import arguments, dataset, load, save
from latent_cell_flow import TEST


@torch.no_grad()
def main(a):
    marks, nets = load(a)
    report = {}
    for case in TEST:
        counts = Counter()

        def visit(m, pairs, run):
            targets = [dst[0] for kind, _, dst in pairs if kind == "empty"]
            for target in targets:
                rng = np.random.default_rng(run + 135)
                for _ in range(8):
                    costs = Counter()
                    token = marks.draw(m, rng, costs)
                    counts["draws"] += 1
                    counts["addressable_output"] += int(token is not None)
                    counts["template_hit"] += int(token is not None and token.rule == target.rule)
                    counts["all_parents_and_template_hit"] += int(token == target)
                    forced = marks.draw(m, rng, costs, oracle_key=(target.rule, False))
                    counts["forced_template_all_parents_hit"] += int(forced == target)
                for name in ("editor", "mask", "flow"):
                    x = sampler(nets[name], marks, m, (), name, 1 if name == "editor" else 4, rng, Counter())
                    counts[name + "_blank"] += int(not x)
                counts["contexts"] += 1

        dataset(a, case, visit)
        report[case] = dict(counts)
    save(a.out / "address-diagnosis.json", report)


if __name__ == "__main__":
    a = arguments()
    torch.set_num_threads(1)
    main(a)
