"""Matched read-gate width pilot with the existing 32-lane Cell KV interface."""

import os

import torch

from exposure_train import output
from foundation_fit import WideRead
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model, train


def run(a, width):
    saved = torch.load(directory(a) / "fits/local-s71-resume.pt", weights_only=False)
    assert saved["progress"][4] == 100000
    previous, old = model(a, saved["config"], 71)
    previous.load_state_dict(saved["model"])
    old.load_state_dict(saved["opt"])
    cfg = dict(saved["config"], name="full", arm="C", read_width=width)
    n, new = model(a, cfg, 71)
    torch.manual_seed(317)
    previous.actor.next_read = WideRead(previous.actor.next_read, width, jitter=0.007)
    n.load_state_dict(previous.state_dict())
    names = dict(n.named_parameters())
    for k, p in previous.named_parameters():
        if p in old.state:
            new.state[names[k]] = old.state[p]
    dest = output(a) / f"read-width-{width}"
    dest.mkdir(exist_ok=True)
    stem = "full-s71"
    resume = dest / (stem + "-resume.pt")
    if not resume.exists():
        saved.update(config=cfg, model=n.state_dict(), opt=new.state_dict())
        tmp = resume.with_suffix(".tmp")
        torch.save(saved, tmp)
        tmp.replace(resume)
        torch.save(n.state_dict(), dest / (stem + "-t100000.pt"))
    os.environ["CELL_TEACHER_FORCING"] = "batched"
    caps = [int(value) for value in os.getenv("CELL_MILESTONES", "130000").split()]
    train(a, cfg, 71, caps, destination=dest)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args(), int(os.environ["CELL_READ_WIDTH"]))
