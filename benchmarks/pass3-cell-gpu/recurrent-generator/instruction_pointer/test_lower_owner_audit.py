import itertools
import unittest
from lower_owner_audit import low_proofs


class BoundTests(unittest.TestCase):
    def test_low_owner_stream_matches_brute_force_without_duplicates(self):
        pools = [[], [(1, 0)], [(2, 0), (3, 1)], [(1, 0), (1, 1), (2, 1)]]
        for domains in itertools.product(pools, repeat=4):
            expected = [
                r for r in itertools.product(*domains) if len({t for t, _ in r}) <= 2
            ]
            self.assertCountEqual(low_proofs(domains), expected)
