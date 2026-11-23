"""Learn the change in continuation state from receiver outcomes on one sealed wave."""
import torch
from torch import nn

from sequence_actor import SequenceActor


class ReceiptActor(SequenceActor):
    requires_receipts = True

    def __init__(self, field_pointer=True):
        super().__init__(field_pointer)
        self.receipt_context = nn.Linear(self.width + 3, self.width)
        self.receipt_update = nn.Linear(self.width, self.width, bias=False)
        nn.init.zeros_(self.receipt_update.weight)

    def correct(self, past, counts):
        normalized = counts / self.lanes.num_embeddings
        signal = self.receipt_context(torch.cat((past, normalized),-1)).tanh()
        return past + self.receipt_update(signal) * counts.sum(-1,keepdim=True).clamp_max(1)

    def after_receipts(self, past, verdicts):
        return self.correct(past, past.new_tensor([self.counts(verdicts)]))

    @staticmethod
    def counts(verdicts):
        return (verdicts.count('accepted'),verdicts.count('duplicate'),
                sum(v not in ('accepted','duplicate','unknown') for v in verdicts))
