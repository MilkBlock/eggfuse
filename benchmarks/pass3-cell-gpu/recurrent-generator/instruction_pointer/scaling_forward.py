"""Trace the teacher-forced forward graph for the exact names seen in the first five fits."""

import json

import torch

from joint_cell_sweep import complete_ce
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model
from scaling_pool import Pool


def run(a):
    d = directory(a)
    out = {}
    for name in ("center", "local", "decoder", "layer01", "layer03"):
        stem = name + "-s71"
        m = json.loads((d / "fits" / (stem + "-t10000.json")).read_text())
        resume = torch.load(d / "fits" / (stem + "-resume.pt"), weights_only=False)
        seen = resume["progress"][0]
        if resume["progress"][4] != 10000:
            raise ValueError("expected first checkpoint")
        n, _ = model(a, m["config"], 71)
        n.load_state_dict(
            torch.load(d / "fits" / (stem + "-t10000.pt"), weights_only=True)
        )
        p = Pool(a, n)
        used = {"actor.lanes.weight"}
        for prefix, module in n.named_modules():
            names = tuple(
                f"{prefix}.{k}" for k, _ in module.named_parameters(recurse=False)
            )
            if names:
                module.register_forward_pre_hook(
                    lambda mod, args, ks=names, seen=used: seen.update(ks)
                )
        for key, targets in seen.items():
            w, s, _ = p.row(key)
            n.prepare(w)
            complete_ce(n, w, n.state(w, s), sorted(targets))
        out[stem + "-t10000"] = {
            "parameters": sum(v.numel() for k, v in n.named_parameters() if k in used),
            "tensors": sorted(used),
            "states": len(seen),
        }
    (d / "forward-replay.json").write_text(json.dumps(out))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
