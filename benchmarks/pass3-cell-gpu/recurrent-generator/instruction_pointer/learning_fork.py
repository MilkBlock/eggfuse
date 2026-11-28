"""Continue the local 100K weights and sampler, preserving AdamW moments by parameter name."""

import os

import torch

from exposure_train import output
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model, train


def run(a):
    path = directory(a) / "fits/local-s71-resume.pt"
    dest = output(a) / "matched-end-to-end"
    dest.mkdir(exist_ok=True)
    saved = torch.load(path, weights_only=False)
    assert saved["progress"][4] == 100000
    cfg = dict(saved["config"], arm="C", name="full")
    resume = dest / "full-s71-resume.pt"
    if not resume.exists():
        previous, old = model(a, saved["config"], 71)
        current, new = model(a, cfg, 71)
        old.load_state_dict(saved["opt"])
        lookup = dict(current.named_parameters())
        for name, param in previous.named_parameters():
            if param in old.state:
                new.state[lookup[name]] = old.state[param]
        saved.update(config=cfg, opt=new.state_dict())
        tmp = resume.with_suffix(".tmp")
        torch.save(saved, tmp)
        tmp.replace(resume)
    os.environ["CELL_TEACHER_FORCING"] = "batched"
    train(a, cfg, 71, [250000, 500000, 1000000], destination=dest)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
