import unittest
from collections import Counter
from types import SimpleNamespace
import torch
from generation_frontier import Threshold
from generation_targets import OutcomeStream, TrainedGenerator


class RawScores:
    def score_children(self, *args):
        return torch.tensor([1.0]), None


class ThresholdProbe(Threshold, RawScores):
    roles = (1, 2)
    study = SimpleNamespace(cut=3.0)


class FrontierTest(unittest.TestCase):
    def test_threshold_only_changes_full_binding(self):
        probe = ThresholdProbe()
        self.assertEqual(probe.score_children(None, 0, None, None)[0].item(), 1.0)
        self.assertEqual(probe.score_children(None, 1, None, None)[0].item(), -2.0)

    def test_productivity_can_only_reorder(self):
        stream = object.__new__(OutcomeStream)
        stream.study = SimpleNamespace(variant="trained")
        stream.stats = Counter()
        stream.priorities = torch.tensor([-99.0, 1.0, 1.0])
        paths = torch.tensor([[2, 7], [2, 9], [3, 0]])
        self.assertEqual(stream.terminal(paths).tolist(), paths[[1, 2, 0]].tolist())
        stream.study.variant = "unranked"
        self.assertTrue(stream.terminal(paths).equal(paths))
        logits = torch.randn(7, 3)
        decision = TrainedGenerator.delta(logits)
        logits[:, 2] = -1e5
        self.assertTrue(decision.equal(TrainedGenerator.delta(logits)))
