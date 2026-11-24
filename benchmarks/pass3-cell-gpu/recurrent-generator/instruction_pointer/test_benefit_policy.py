import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch
import torch
from benefit_policy import BenefitNet, BenefitStream


class BenefitTests(unittest.TestCase):
    def test_zero_initial_and_protected_final_admission(self):
        net = BenefitNet()
        base = torch.tensor([-1.0, 1.0])
        args = (
            torch.zeros(2, 4),
            torch.zeros(2, 24),
            torch.zeros(2, 39),
            base,
            torch.ones(2),
        )
        torch.testing.assert_close(net.prediction(*args, "residual"), base)
        with torch.no_grad():
            net.correction[-1].bias.fill_(-2)
        torch.testing.assert_close(net.prediction(*args, "residual"), base)
        torch.testing.assert_close(net.prediction(*args, "full"), base - 2)

    def test_typed_receipts_align_to_successful_parent(self):
        s = object.__new__(BenefitStream)
        s.evidence = {1: (4, None)}
        s.result_raw = torch.arange(3 * 39).reshape(3, 39).float()
        s.remember_response(1, torch.tensor([3, 1]), torch.tensor([True, False, True]))
        raw = s.evidence[1][1]
        torch.testing.assert_close(raw[[3, 1]], s.result_raw[[0, 2]])
        self.assertFalse(raw[[0, 2]].any())

    def test_deployed_decoder_cannot_use_compiled_program_catalog(self):
        stream = object.__new__(BenefitStream)
        stream.study = SimpleNamespace(collect=False, agent=BenefitNet())
        stream.rd = SimpleNamespace(
            iface=SimpleNamespace(rules=[{"query": [{"call": {"primitive": {}}}]}])
        )
        stream.rule = 0
        stream.stats = Counter()
        stream.transaction = SimpleNamespace(capacity=256)
        with (
            patch("benefit_policy.plans", side_effect=AssertionError),
            patch("benefit_policy.decode", return_value=[]) as decoder,
        ):
            self.assertEqual(stream.programs(1), [])
            decoder.assert_called_once()
