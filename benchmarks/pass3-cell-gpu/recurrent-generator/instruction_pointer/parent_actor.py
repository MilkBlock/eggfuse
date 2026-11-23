"""Read the Actor's own named requests and wave receipts during parent selection."""
from collections import defaultdict

import torch
from torch import nn

from receipt_actor import ReceiptActor


class ParentHistory:
    """Private to one sealed Run. Indices address the unchanged token/port memory."""
    def __init__(self, lookup, head):
        self.lookup = lookup
        self.head = head
        self.records = defaultdict(dict)

    def update(self, rid, refs, bucket, delta):
        indices = tuple(self.lookup[a] for a in refs)
        counts = self.records[rid].setdefault(indices, [0, 0, 0, 0])
        counts[bucket] += delta
        if counts[bucket] < 0:
            raise ValueError('receipt without a pending request')

    def issue(self, rid, refs):
        self.update(rid, refs, 0, 1)

    def resolve(self, wave, verdicts):
        for (rid, refs), verdict in zip(wave, verdicts, strict=True):
            if verdict == 'unknown':
                continue
            bucket = 1 if verdict == 'accepted' else 2 if verdict == 'duplicate' else 3
            self.update(rid, refs, 0, -1)
            self.update(rid, refs, bucket, 1)

    def features(self, rid, roles, selected, scores):
        # Rows are the model's own prior requests for this rule. A candidate
        # reads counts for its address at this role, and counts with the same
        # already-selected parent prefix. No values from graph rows are compared.
        features = scores.new_zeros((*scores.shape, 8))
        records = self.records.get(rid)
        if records:
            addresses = torch.tensor(list(records), device=scores.device, dtype=torch.long)
            counts = scores.new_tensor(list(records.values()))
            same_prefix = counts.new_zeros((len(records), 1))
            if selected:
                chosen_roles, chosen_indices = zip(*selected)
                same_prefix = (addresses[:, list(chosen_roles)] ==
                               addresses.new_tensor(chosen_indices)).all(-1,keepdim=True)
            evidence = torch.cat((counts, counts * same_prefix), -1)
            for row, role in enumerate(roles):
                features[row].index_add_(0, addresses[:,role], evidence)
        return features.log1p()

    def __call__(self, rid, roles, selected, scores):
        if rid not in self.records:
            return scores
        return scores + self.head(self.features(rid, roles, selected, scores)).squeeze(-1)


class ParentActor(ReceiptActor):
    conditioned_parents = True

    def __init__(self, field_pointer=True):
        super().__init__(field_pointer)
        self.parent_read = nn.Linear(8, 1, bias=False)
        nn.init.zeros_(self.parent_read.weight)

    def parent_history(self, lookup):
        return ParentHistory(lookup, self.parent_read)
