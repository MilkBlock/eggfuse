"""Causality, projection and parameter-tying contracts for single-row emission."""
import unittest

import torch

from decoder import OneRowDecoder


class DecoderContract(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(97)
        self.width = 12
        self.a = torch.randint(8, (3, 4, 3))
        self.b = torch.randint(8, (3, 4, 2))
        self.requests = torch.randint(8, (3, 4, 3))
        self.ports = torch.randn(3, 2, 2, self.width)
        self.make = [(1, 0), (0, 2), (2, -3)]
        self.finish = [(0, 0), (1, 2), (0, 2), (0, 1)]
        self.args = (self.a, self.b, self.requests, self.ports, self.make, self.finish, (0, 1))

    def build(self, shared):
        torch.manual_seed(93)
        return OneRowDecoder(self.width, num_rules=4, shared_heads=shared, max_columns=6, slots=5)

    def test_only_head_tying_changes(self):
        shared, untied = self.build(True), self.build(False)
        self.assertEqual(len(shared.heads), 1)
        self.assertEqual(len(untied.heads), 4)
        for name, value in shared.state_dict().items():
            torch.testing.assert_close(value, untied.state_dict()[name], rtol=0, atol=0)
        for head in untied.heads:
            for key, parameter in head.state_dict().items():
                torch.testing.assert_close(parameter, shared.heads[0].state_dict()[key], rtol=0, atol=0)
        one_shared, token_shared = shared(*self.args)
        one_untied, token_untied = untied(*self.args)
        torch.testing.assert_close(token_shared, token_untied, rtol=0, atol=0)
        for s, t in zip(one_shared, one_untied):
            for key in s:
                torch.testing.assert_close(s[key], t[key], rtol=0, atol=0)
        # A rule outside this batch gets no independent gradient; tied scoring
        # accumulates both stages' gradients into the same parameter tensors.
        loss = sum(stage['left_logits'].square().mean() + stage['right_logits'].square().mean()
                   for stage in one_untied)
        loss.backward()
        self.assertGreater(float(untied.heads[0].key.weight.grad.abs().sum()), 0)
        self.assertGreater(float(untied.heads[1].key.weight.grad.abs().sum()), 0)
        self.assertIsNone(untied.heads[2].key.weight.grad)
        self.assertIsNone(untied.heads[3].key.weight.grad)

    def test_history_changes_later_positions_only(self):
        model = self.build(True).eval()
        (actual, _), token = model(*self.args)
        (blind, _), _ = model(*self.args, history=False)
        for key in actual:
            torch.testing.assert_close(actual[key][:, 0], blind[key][:, 0], rtol=0, atol=0)
        self.assertTrue((actual['hidden'][:, 1:] != blind['hidden'][:, 1:]).any())
        torch.testing.assert_close(token[..., :self.width], actual['hidden'], rtol=0, atol=0)
        torch.testing.assert_close(token[..., model.payload_offset:model.payload_offset + len(self.make)],
                                   actual['rows'].float(), rtol=0, atol=0)

    def test_finish_resumes_from_generated_row_and_compiled_projection(self):
        model = self.build(True).eval()
        (first, second), token = model(*self.args)
        graph = torch.arange(len(self.a))[:, None]
        li, ri = first['pointers'].unbind(-1)
        expected = torch.stack((self.b[graph, ri, 0], self.a[graph, li, 2], torch.full_like(li, -3)), dim=-1)
        torch.testing.assert_close(first['rows'], expected)
        resumed = model.finish_from(token, self.requests, self.ports[:, 1], len(self.make), self.finish, 1)
        for key in second:
            torch.testing.assert_close(second[key], resumed[key], rtol=0, atol=0)
        # Inject a poison payload into the emitted frontier only. Its projected
        # column must appear in every selected downstream row, even for nulls.
        altered = token.clone()
        altered[..., model.payload_offset] = -17
        replay = model.finish_from(altered, self.requests, self.ports[:, 1], len(self.make), self.finish, 1)
        self.assertTrue((replay['rows'][..., 0] == -17).all())


if __name__ == '__main__':
    torch.set_num_threads(1)
    unittest.main()
