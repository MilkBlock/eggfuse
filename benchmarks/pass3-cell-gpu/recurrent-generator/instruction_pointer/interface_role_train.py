import os

import torch

from interface_role_model import RoleRead
from operand_read_model import words
from partner_index_worlds import args
from value_read_train import mode, training


def dest(a):
    path = a.out / "interface-role"
    path.mkdir(exist_ok=True)
    return path


if __name__ == "__main__":
    torch.set_num_threads(1)
    assert mode() == "rich"
    training(
        args(),
        factory=RoleRead,
        variants=os.environ.get("ROLE_ARMS", "BC"),
        features=words,
        destination=dest,
    )
