from collections import Counter, defaultdict
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np
import torch

from structure_recipe import fanout, validate_program
from structure_runtime import Instance, PointerEntries, StructureEntries


class StructureTests(TestCase):
    def test_static_read_requires_prior_publication(self):
        header = (0, 0, ((-1, -1, -1), (-2, -1, -1)))
        with self.assertRaisesRegex(ValueError, "before publication"):
            validate_program([header, (1, 0, ((0, 0, 2),))])
        validate_program([header, (1, 1, ((0, 0, 2),))])

    def test_existing_pointer_ranks_only_open_distinct_watermark_eligible_receipts(self):
        policy = PointerEntries.__new__(PointerEntries)
        policy.rules = {0: 6}
        policy.count = Counter()
        ptr = Mock()
        ptr.logits.side_effect = [(None, torch.zeros(1, 2)), (torch.tensor([2.0, 1.0]), None)]
        policy.pointers = {(0, (1, 0)): ptr}
        policy.parent_model = Mock()
        policy.parent_model.start.return_value = torch.zeros(2)
        mem = Mock()
        mem.rd.iface.rules = [{"metadata": {"seminaive": True}}]
        mem.bank.return_value.positions = {(5, 0): 22, (6, 0): 24}
        recent = dict.fromkeys([(1, 0, 7), (3, 0, 5), (5, 0, 6), (6, 0, 7)])
        ref = policy.open_partner(0, 1, 12, (1, 2, 3), (0, 9), recent, mem, "Compose")
        self.assertEqual(ref, (5, 0, 6))
        self.assertEqual(ptr.logits.call_args.args[2].tolist(), [[12, 22], [12, 24]])
        self.assertEqual(policy.count["open_partner_scores"], 2)
        self.assertEqual(policy.count["open_interface_probes"], 4)

    def fixture(self):
        p = StructureEntries.__new__(StructureEntries)
        entry = (-2, -1, -1)
        read_first = (0, 0, 3)
        plan = (
            (0, 0, ((-1, -1, -1), entry)),
            (1, 1, (read_first, entry)),
            (2, 1, (read_first, entry)),
            (3, 2, ((2, 0, 4), entry)),
        )
        p.programs = {0: plan}
        p.rules = {1: 1, 2: 1}
        p.txn = NS(run=2)
        p.pending, p.publish_next, p.members = [], [], {}
        p.covered_indices, p.covered_rules, p.done = {}, {}, defaultdict(set)
        p.count, p.suffix_tokens = Counter(), {}
        p.suffix_positions, p.struct_positions = defaultdict(set), defaultdict(dict)
        p.observed = {(10, 3): (10, 3, 2)}
        mem = Mock()
        mem.roles = {i: (1, 1) for i in range(4)}
        mem.rd.iface.rules = [{"metadata": {"seminaive": True}}] * 4
        mem.rd.store.visible = {(10, 3): {"table": 1, "version": 2}, (7, 1): {"table": 1, "version": 1}}
        mem.bank.return_value.positions = {(10, 3): 0, (7, 1): 1, (12, 4): 2}
        inst = Instance(0, "Compose", 2, {entry: (7, 1, 1)}, [10], 2)
        return p, mem, inst

    @patch("structure_runtime.send")
    def test_parallel_consumers_then_next_publication_no_new_binding(self, send):
        p, mem, inst = self.fixture()
        send.side_effect = [np.array([[n, 0]]) for n in (11, 12, 13)]
        p.advance(inst, mem)
        self.assertEqual([call.args[1] for call in send.call_args_list], [1, 2])
        self.assertTrue(fanout(p.programs[0], 2))
        self.assertEqual(inst.tokens, [10, 11, 12])
        p.resume_programs(mem)
        self.assertEqual(send.call_count, 2)
        p.txn.run += 1
        p.rules = {3: 3}
        p.observed[12, 4] = (12, 4, 3)
        mem.rd.store.visible[12, 4] = {"table": 1, "version": 3}
        p.resume_programs(mem)
        self.assertEqual(inst.tokens, [10, 11, 12, 13])
        self.assertEqual(p.pending, [])
        self.assertEqual(p.count["structure_wired_reads"], 6)
        self.assertEqual(p.suffix_tokens[12], ("fanout", 2))
        self.assertEqual(p.count["structure_completed"], 1)

    @patch("structure_runtime.send")
    def test_stale_return_preserves_residual(self, send):
        p, mem, inst = self.fixture()
        mem.rd.store.visible[10, 3]["version"] += 1
        p.advance(inst, mem)
        send.assert_not_called()
        self.assertEqual(p.count["structure_unavailable_return"], 1)
        self.assertFalse(p.covered_rules)

    @patch("structure_runtime.send")
    def test_rejected_branch_never_skips_residual(self, send):
        p, mem, inst = self.fixture()
        send.return_value = np.array([[0, 1]])
        p.advance(inst, mem)
        self.assertEqual(send.call_count, 1)
        self.assertFalse(p.covered_rules)
        self.assertFalse(p.suffix_tokens)
