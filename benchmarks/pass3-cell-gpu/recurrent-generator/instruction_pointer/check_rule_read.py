"""Compare grouped port reductions with a per-atom read at the source rule watermark."""
import argparse
from dataclasses import replace
import math
from pathlib import Path

import torch

from history import stream
from rule_read import RuleReadActor


@torch.no_grad()
def check(directory, runs):
    torch.set_num_threads(1)
    model = RuleReadActor('typed', mask_anchors=True).eval()
    checked = 0
    partial_windows = 0
    for catalog, frame in stream(directory, 17, runs):
        mem = model.memory(catalog, frame)
        for row, (rule, watermark) in enumerate(frame.rules.items()):
            expected = mem.keys.new_zeros(2 * model.width + 2)
            atoms = catalog.atoms[rule]
            available = not atoms and (not catalog.seminaive[rule] or watermark == 0)
            for table, role in atoms:
                indices = [i for i, p in enumerate(mem.ports) if p.table == table]
                delta = [i for i in indices if not catalog.seminaive[rule]
                         or mem.ports[i].version >= watermark]
                available |= bool(delta)
                partial_windows += int(len(indices) > len(delta) > 0)
                for side, selection in enumerate((indices, delta)):
                    if selection:
                        start = side * model.width
                        expected[start:start + model.width] += mem.nodes[role].tanh() * mem.keys[selection].mean(0)
                        expected[2 * model.width + side] += math.log1p(len(selection))
            assert bool(mem.rule_support[row]) == available
            torch.testing.assert_close(mem.rule_inputs[row, model.width:], expected / max(1, len(atoms)))
            checked += 1
        reverse = replace(frame, ports=list(reversed(frame.ports)))
        other = model.memory(catalog, reverse, mem.nodes)
        torch.testing.assert_close(other.rule_inputs, mem.rule_inputs)
        assert torch.equal(other.rule_support, mem.rule_support)
    if not checked or not partial_windows:
        raise ValueError('selected Runs did not exercise a partially fresh table')
    print(f'{checked} rule snapshots; {partial_windows} partially fresh atom windows')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('runs', type=int, nargs='+')
    args = p.parse_args()
    check(args.directory, set(args.runs))
