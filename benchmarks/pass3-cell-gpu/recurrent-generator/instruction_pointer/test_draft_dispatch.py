import unittest
from collections import Counter
from types import SimpleNamespace

import numpy as np
import torch

from discrete_cells import Marks
from discrete_draft import Cell, Item, Local
from draft_dispatch import Dispatch, correlate, dependency_free, settle
from latent_cell_flow import ZERO


class DraftTests(unittest.TestCase):
    def test_native_ids_not_page_positions(self):
        a, b = Item(7, Cell(375, ())), Item(0, Cell(574, ()))
        out = correlate({31: a, 32: b}, [[32, 0], [31, 1]])
        self.assertEqual(out, {0: [32, 0], 7: [31, 1]})
        for rows in ([[31, 0]], [[31, 0], [31, 0]], [[7, 0], [0, 0]]):
            with self.assertRaises(ValueError):
                correlate({31: a, 32: b}, rows)

    def test_receipt_is_not_publication(self):
        items = (Item(4, Cell(1, (Local(8, 3),))),)
        unissued = settle(items, {8: [32, 0]})
        self.assertEqual(unissued[0].cell.refs, ((32, 3, -1),))
        self.assertFalse(dependency_free(unissued[0]))
        self.assertEqual(settle(items, {}), items)

    def test_rejected_page_dependencies_closed_without_credit(self):
        policy = object.__new__(Dispatch)
        policy.delayed = []
        st = Counter()
        p = Item(1, Cell(1, ((0, 2, -1),)))
        c = Item(2, Cell(2, (Local(1, 0),)))
        other = Item(3, Cell(2, ((34, 2, -1),)))
        policy.keep_dependencies([p, c, other], st)
        self.assertEqual(policy.delayed, [(other,)])
        self.assertEqual(st, {"unissued_failed_dependency": 2})

    def test_empty_and_nonempty_arity_share_template_draw(self):
        marks = Marks()
        for high in [False, True]:
            key = (574, high)
            m = SimpleNamespace(
                ids=[key],
                ids_index={key: 0},
                roles={574: ()},
                context=lambda: ZERO,
                graph=lambda _: ZERO,
            )
            cell = marks.draw(m, np.random.default_rng(1), Counter())
            self.assertEqual(cell, Cell(574, (), high))

    def test_sparse_selection_ignores_blocked_head(self):
        policy = object.__new__(Dispatch)
        policy.mode = "set"
        policy.current = 5
        policy.scheduled = {574: 0, 3: 1}
        policy.journal = []
        policy.select_rng = np.random.default_rng(0)
        net = torch.nn.Linear(len(ZERO) * 5 + 6, 3)
        net.weight.data.zero_()
        net.bias.data.fill_(-50)
        policy.nets = {"flow": net}
        policy.m = SimpleNamespace(state=ZERO, event=ZERO, embed=lambda _: ZERO)
        bad = Item(8, Cell(375, ()))
        valid = Item(3, Cell(574, ()))
        # Validity of already named runtime references is the verifier's job.
        wrong = Item(6, Cell(3, ((999, 2, 0),)))
        self.assertEqual(
            policy.dispatch_prefix((bad, valid, wrong), Counter()), (valid, wrong)
        )
        self.assertEqual(policy.draft, (bad,))

    def test_frozen_relative_readout_can_retain_legal_head_and_issue_two(self):
        policy = object.__new__(Dispatch)
        policy.mode = "relative"
        policy.current = 1
        policy.scheduled = {10: 0, 11: 0, 12: 0}
        policy.journal = []
        rate = torch.nn.Linear(len(ZERO) * 5 + 6, 3)
        with torch.no_grad():
            rate.weight.zero_()
            rate.bias.zero_()
            rate.weight[1:, 2 * len(ZERO)] = 1
        policy.nets = {"flow": rate}
        values = {10: 8.0, 11: -4.0, 12: -8.0}
        policy.m = SimpleNamespace(
            state=ZERO,
            event=ZERO,
            embed=lambda c: torch.full_like(ZERO, values[c.rule]),
        )
        items = tuple(Item(i, Cell(r, ())) for i, r in enumerate(values))
        self.assertEqual(policy.dispatch_prefix(items, Counter()), items[1:])
        self.assertEqual(policy.draft, items[:1])


if __name__ == "__main__":
    unittest.main()
