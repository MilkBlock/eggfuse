import unittest
from unittest.mock import patch
import torch
from generation_higher import Layouts


class HigherCellTest(unittest.TestCase):
    def test_higher_boundary_fully_named_before_issuance(self):
        units = [
            ((0, 0, ((-1, 0),)), (1, 1, ((0, 2), (-1, 0)))),
            ((0, 0, ((-1, 0),)), (1, 1, ((0, 2), (-1, 1)))),
            ((0, 0, ()), (2, 1, ())),
        ]
        meta = dict(catalog="key", codes="key", signatures=("a", "b", "absent"))
        with (
            patch("generation_higher.read", side_effect=[meta, {}]),
            patch("generation_higher.digest", return_value="key"),
            patch("generation_higher.signatures", return_value=["b", "a"]),
            patch("generation_higher.unpack", return_value=units),
            patch(
                "generation_higher.torch.load", return_value={"codes": torch.ones(3, 8)}
            ),
        ):
            catalog = Layouts({})
        self.assertEqual(catalog.original, [0])
        self.assertEqual(catalog.by[1], [0])
        self.assertEqual(catalog.units[0][1], (0, 1, ((0, 2), (-1, 0))))
