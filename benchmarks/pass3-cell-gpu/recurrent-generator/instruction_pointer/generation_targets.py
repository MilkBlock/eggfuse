"""Cell admission and output ordering on a frozen Cell Stream."""

import torch
from torch import nn
from generation_frontier import Generator
from txn_policy import ResponseStream


class OutcomeNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Linear(24 + 36 + 4 + 1, 48), nn.Tanh(), nn.Linear(48, 32), nn.Tanh()
        )
        self.outcomes = nn.Linear(32, 3)

    def forward(self, x):
        return self.outcomes(self.features(x))

    @staticmethod
    def inputs(stream, z, base, depth, p):
        return torch.cat(
            (
                z,
                stream.local(depth, p),
                stream.rd.meta(stream.rule).expand(len(p), -1),
                base[:, None] / 8,
            ),
            1,
        )


class OutcomeStream(ResponseStream):
    def score_children(self, h, depth, p, parents):
        score, z = self.logits(h, depth, p)
        if depth + 1 != len(self.roles):
            return score, z
        logits = self.study.outcomes(OutcomeNet.inputs(self, z, score, depth, p))
        # The productivity channel is used only to permute survivors. In
        # particular it cannot veto a legal certificate at any iteration.
        result = score + self.study.delta(logits) - self.study.cut
        self.priorities = logits[result >= 0, 2]
        return result, z

    def terminal(self, paths):
        if self.study.variant == "trained" and len(paths) > 1:
            order = self.priorities.argsort(descending=True, stable=True)
            self.stats["positions_reordered"] += int(
                (order != torch.arange(len(order))).sum()
            )
            return paths[order]
        return paths


class TrainedGenerator(Generator):
    @staticmethod
    def delta(logits):
        return (logits[:, 0] + 0.5 * logits[:, 1]).clamp(-12, 12)

    def __init__(self, root, out, arm, cut, case):
        super().__init__(root, arm, cut, case)
        self.stream_type = OutcomeStream
        self.outcomes = OutcomeNet().eval()
        self.outcomes.load_state_dict(
            torch.load(out / "outcomes.pt", weights_only=True)
        )
