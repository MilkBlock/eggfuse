from collections import Counter
from types import SimpleNamespace
import unittest

import torch

from prefix_service import ServiceStream
from template_routing import RouteNet, Router
from tree_routing import TreeNet, TreeRouter, tree


class SparseRoutingTests(unittest.TestCase):
    def test_compiled_tree_paths_return_all_and_only_eligible_layouts(self):
        codes = torch.zeros(9, 4)
        eligible = [8, 0, 2, 6, 3]
        root, _, children, paths = tree(codes, eligible)
        for uid, choices in paths.items():
            node = root
            for expected, bit in choices:
                self.assertEqual(node, expected)
                node = int(children[node, bit])
            self.assertEqual(-1 - node, uid)
        self.assertEqual(set(paths), set(eligible))
        r = TreeRouter.__new__(TreeRouter)
        r.codes = codes
        r.net = TreeNet(4)
        compiled = r.prepare([0])
        counts = Counter()
        with torch.no_grad():
            for weight in r.net.parameters():
                weight.zero_()
            r.net.gate[-1].bias.fill_(-1)
            self.assertEqual(
                r.select(torch.zeros(3, 28), compiled, counts).tolist(), [-1] * 3
            )
            r.net.gate[-1].bias.fill_(1)
            self.assertEqual(
                r.select(torch.zeros(3, 28), compiled, counts).tolist(), [0] * 3
            )
        self.assertEqual(counts["tree_decisions"], 0)

    def test_factorized_route_elides_invariant_address_bits(self):
        r = Router.__new__(Router)
        r.depth = 2
        r.n = 3
        r.net = RouteNet(3, 2)
        r.mode = "sparse"
        r.cache = {}
        r.limit = None
        r.cat = SimpleNamespace(original=[0, 1, 2])
        r.codes = {0: (0,), 1: (1, 0), 2: (1, 1)}
        r.powers = 2 ** torch.arange(2)
        counts = Counter()
        with torch.no_grad():
            for weight in r.net.parameters():
                weight.zero_()
            r.net.use.bias.fill_(1)
            r.net.bits.bias.copy_(torch.tensor([-1.0, 1.0]))
            compiled = r.prepare([1, 2])
            self.assertEqual(
                r.select(torch.zeros(4, 28), compiled, counts).tolist(), [2] * 4
            )
            self.assertEqual(counts["address_bits"], 4)

    def test_fine_postings_keep_collision_and_rule_delta(self):
        s = ServiceStream.__new__(ServiceStream)
        s.study = SimpleNamespace(
            service="fresh-fine",
            planes=torch.ones(24, 8),
            bits_weight=2 ** torch.arange(8),
        )
        s.stats = Counter()
        s.semi = True
        s.fine = {}
        s.urgency = {1: torch.tensor([True, True])}
        s.roles = [[(1, 0), (2, 0)], [(3, 0), (4, 0), (5, 0)]]
        keys = {p: (None, [j], [17]) for j, p in enumerate(sum(s.roles, []))}
        s.rd = SimpleNamespace(index=SimpleNamespace(rows=keys))
        s.tables = [
            (torch.tensor(age), None, None, torch.ones(len(age), 1, 24))
            for age in ([False, True], [False, True, False])
        ]
        s.links = [[], [(0, 0, 0)]]
        s.programs = lambda depth: ()
        pairs = [
            (a, b)
            for ids, cols in s.children(torch.tensor([[0], [1]]), 1, 2)
            for a, b in zip(ids.tolist(), cols.tolist())
        ]
        self.assertEqual(pairs, [(0, 1), (1, 0), (1, 1), (1, 2)])
        self.assertEqual(s.stats["serviced_deferred"], 2)
