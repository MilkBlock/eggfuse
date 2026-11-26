import unittest
from types import SimpleNamespace
import torch
from discrete_draft import Cell, Item
from fine_fit import scope_loss
from throughput_slots import SlotLog


class ThroughputTests(unittest.TestCase):
    def test_partial_is_observed_without_inventing_a_cell(self):
        page = SimpleNamespace(
            slots=2, m=SimpleNamespace(roles=[(), (1, 1)]), addresses={1: (-5, 7)}
        )
        # Slot 1 bound its first reference, then found an empty second typed table.
        # Two zero-parent marks survive, only one fits the remaining request allocation.
        rows = torch.tensor(
            [
                [7, 0, 0, 0, 0, 0, 0, 0],
                [25, -1, 1, 0, 3, 0, 0, 0],
                [7, 0, 0, 0, 0, 0, 0, 0],
            ]
        )
        log = SlotLog(retain_page=True)
        log.draw(page, rows, [Item(1, Cell(0, ())), Item(0, Cell(0, ()))])
        log.quota(1, 2)
        self.assertEqual(log.last_page[1], [2, 4, [(-5, 7, 3)]])
        self.assertEqual(log.summary()["counts"]["over_goal"], 1)
        self.assertEqual(log.totals["empty_typed_table"], 1)
        self.assertEqual(log.totals["returned"], 1)

    def test_inactive_and_unknown_do_not_directly_label_parents(self):
        a, b = Cell(0, ()), Cell(1, ())
        factors = torch.tensor([[0.2, 0.4], [0.3, 0.7]], requires_grad=True)
        rec = dict(
            positive={},
            self_positive=set(),
            inactive={a},
            bad_binding=set(),
            control="seal",
            unknown={b},
            physical={b},
        )
        scope_loss(factors, {a: 0, b: 1}, rec, 16, "witness").backward()
        torch.testing.assert_close(factors.grad, torch.tensor([[1.0, 0.0], [0.0, 0.0]]))

    def test_bad_binding_conditions_on_detached_template(self):
        a = Cell(0, ())
        factors = torch.tensor([[0.2, 0.4]], requires_grad=True)
        rec = dict(positive={}, self_positive=set(), inactive=set(), bad_binding={a})
        scope_loss(factors, {a: 0}, rec, 16, "witness").backward()
        torch.testing.assert_close(factors.grad, torch.tensor([[0.0, 0.2]]))


if __name__ == "__main__":
    unittest.main()
