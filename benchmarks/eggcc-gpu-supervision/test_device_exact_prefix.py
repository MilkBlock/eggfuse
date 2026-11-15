import itertools
import unittest

import mlx.core as mx
import numpy as np

from device_exact_prefix import expand_exact


class ExactPrefixTests(unittest.TestCase):
    def run_case(self, labels, rows, capacity=64, xp=mx):
        atoms, ports = labels.shape
        flat = labels.reshape(-1)
        required = (flat[:, None] >= 0) & (flat[None, :] >= 0) & (flat[:, None] == flat[None, :])
        pools = [
            dict(roots=xp.array(values),
                 entries=xp.array([[i, 0] for i in range(len(values))]),
                 live=xp.ones(len(values), dtype=xp.bool_))
            for values in rows
        ]
        output = expand_exact(pools, xp.array(required), atoms, ports, capacity, xp)
        actual = {tuple(row[:, 0]) for row in np.array(output["entries"])[np.array(output["live"])]}
        expected = set()
        for indices in itertools.product(*(range(len(values)) for values in rows)):
            bindings = {}
            valid = True
            for atom, row in enumerate(indices):
                for field, variable in enumerate(labels[atom]):
                    if variable < 0:
                        continue
                    value = rows[atom][row, field]
                    if value < 0 or (variable in bindings and bindings[variable] != value):
                        valid = False
                    bindings[variable] = value
            if valid:
                expected.add(indices)
        return output, actual, expected

    def test_randomized_matches_against_independent_enumeration(self):
        rng = np.random.default_rng(27)
        for _ in range(24):
            labels = rng.integers(0, 4, (3, 2), dtype=np.int32)
            rows = [rng.integers(0, 5, (4, 2), dtype=np.int32) for _ in range(3)]
            for xp in (np, mx):
                result, actual, expected = self.run_case(labels, rows, xp=xp)
                self.assertTrue(bool(result["complete"]))
                self.assertEqual(actual, expected)

    def test_repeated_variable_padding_and_empty_match(self):
        labels = np.array([[0, 0], [0, -1]])
        rows = [np.array([[1, 1], [1, 2], [-1, -1]]), np.array([[1, -1], [3, -1]])]
        result, actual, expected = self.run_case(labels, rows)
        self.assertTrue(bool(result["complete"]))
        self.assertEqual(actual, {(0, 0)})
        self.assertEqual(actual, expected)

    def test_intermediate_overflow_cannot_claim_empty_completion(self):
        labels = np.array([[0], [0]])
        rows = [np.array([[1], [2], [3]]), np.array([[9]])]
        result, actual, expected = self.run_case(labels, rows, capacity=2)
        self.assertFalse(bool(result["complete"]))
        self.assertTrue(bool(result["overflow"]))
        self.assertEqual(actual, expected)

    def test_selective_prefix_avoids_full_tuple_materialization(self):
        labels = np.array([[0], [0], [0]])
        rows = [np.arange(16, dtype=np.int32)[:, None]] * 3
        result, actual, expected = self.run_case(labels, rows, capacity=16)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 16)
        self.assertEqual(int(result["active_choices"]), 528)
        self.assertEqual(int(result["scheduled_choices"]), 768)
        self.assertEqual(int(result["rejected_choices"]), 480)


if __name__ == "__main__":
    unittest.main()
