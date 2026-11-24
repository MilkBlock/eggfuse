"""Can the joint terminal choose a successful held wiring before root binding?"""

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
import torch
from entry_model import samples, scores
from event_templates import BranchNet
from receipt_bake import save


def evaluate(data, root, out):
    report = {}
    for name in ("dot", "fact", "loopfact", "sum-divisors"):
        masks = []
        groups = samples(data, root / name, out, name, 937, False, held_masks=masks)
        report[name] = {}
        for which, path in (
            ("frozen", Path("run-recall/cell-events/template.pt")),
            ("trained", out / "entry.pt"),
        ):
            model = BranchNet().eval()
            model.load_state_dict(torch.load(path, weights_only=True))
            stats = Counter()
            for (x, c, y), mask in zip(groups, masks, strict=True):
                selected = scores(model, x, c).argmax(1)
                wanted = y[:, mask].sum(1) > 0
                match = y.gather(1, selected[:, None]).flatten() > 0
                stats["held_positive_contexts"] += int(wanted.sum())
                stats["chose_supported_held"] += int(
                    (wanted & match & mask[selected]).sum()
                )
                stats["chose_any_supported"] += int((wanted & match).sum())
            report[name][which] = stats
    save(out / "unseen.json", report)


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "root", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    with torch.no_grad():
        evaluate(a.data, a.root, a.out)
