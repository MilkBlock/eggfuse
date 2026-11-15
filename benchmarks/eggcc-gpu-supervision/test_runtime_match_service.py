import unittest

import numpy as np

from runtime_match_service import select


class RuntimeFilterTests(unittest.TestCase):
    def test_typed_id_equality_bound_columns_and_repeats(self):
        rng = np.random.default_rng(91)
        for _ in range(30):
            rows = rng.integers(0, 16, (73, 5)).tolist()
            bound = rng.integers(-1, 4, 5).tolist()
            live = (rng.random(73) > 0.2).tolist()
            pairs = [(0, 2), (2, 4)]
            actual = select(dict(rows=rows, bound=bound, live=live, equal=pairs))
            expected = [
                active and all(b < 0 or value == b for value, b in zip(row, bound))
                and all(row[a] == row[b] for a, b in pairs)
                for row, active in zip(rows, live)
            ]
            self.assertEqual(actual, expected)

    def test_ids_above_float_exact_integer_limit(self):
        rows = [[16777216, 16777217], [16777217, 16777217]]
        self.assertEqual(select(dict(rows=rows, bound=[-1, -1], live=[True, True], equal=[(0, 1)])),
                         [False, True])


if __name__ == "__main__":
    unittest.main()
