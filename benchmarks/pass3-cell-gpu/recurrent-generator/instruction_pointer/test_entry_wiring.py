"""Regressions for the 48-layout entry selector and censored rank labels."""
from pathlib import Path
import unittest

import torch

from entry_model import scores
from entry_wiring import terminal_codes
from event_templates import BranchNet
from receipt_bake import read

REPORT = Path(__file__).parent / "run-recall"


class EntryWiringTest(unittest.TestCase):
    def test_same_root_different_return_reaches_b_terminal(self):
        layouts = read(REPORT / "entry-first/entry/catalog.json")["layouts"]
        a, b = 25, 34
        self.assertEqual(layouts[a][0], layouts[b][0])
        self.assertEqual(layouts[a][1][:2], layouts[b][1][:2])
        self.assertNotEqual(layouts[a][1][2], layouts[b][1][2])
        path = REPORT / "entry-wiring"
        graph = torch.load(path / "graph.pt", weights_only=True)
        code = torch.from_numpy(terminal_codes(graph["baked"][[a, b]], 0))
        self.assertFalse(torch.equal(code[0], code[1]))
        net = BranchNet().eval()
        net.load_state_dict(torch.load(REPORT / "cell-events/template.pt", weights_only=True))
        event = torch.zeros((1, 16))
        logits = scores(net, event, code)
        self.assertNotEqual(logits[0, 0].item(), logits[0, 1].item())
        torch.testing.assert_close(scores(net, event, code.flip(0)), logits.flip(1))
