import os

import torch

from operand_read_model import OperandRead, words
from partner_index_worlds import args
from value_read_train import mode, training


def dest(a):
    path = a.out / "operand-read"
    path.mkdir(exist_ok=True)
    return path


if __name__ == "__main__":
    torch.set_num_threads(1)
    assert mode() == "rich"
    training(
        args(),
        factory=OperandRead,
        variants=os.environ.get("OPERAND_ARMS", "BCD"),
        features=words,
        destination=dest,
    )
