import unittest
from unittest.mock import patch

import torch

from continuous_stream import Stream
from scaling_eval import OfflineInactiveWindow


class DefaultCacheTests(unittest.TestCase):
    def test_native_session_scopes_cache_even_on_failure(self):
        from test_incremental_kv import CacheTest

        fixture = CacheTest()
        fixture.setUp()
        n = fixture.n
        with torch.no_grad():
            p = Stream(n, "A")
            with self.assertRaises(ArithmeticError), p.inference_session():
                self.assertIsNotNone(p.memory_cache)
                self.assertIn("published_kv", vars(n))
                raise ArithmeticError
            self.assertNotIn("published_kv", vars(n))
            self.assertNotIn("response_kv", vars(n))
            with Stream(n, "A", incremental=False).inference_session():
                self.assertNotIn("published_kv", vars(n))
        with Stream(n, "A").inference_session():
            self.assertNotIn("published_kv", vars(n))

    def test_diagnostic_only_intercepts_fully_inactive_constructible_entries(self):
        from types import SimpleNamespace

        w = SimpleNamespace(layouts=[[(0,)], [(1,)]], roles=[[], [1]])
        s = {
            "menu": [0, 1],
            "ports": [],
            "check_dirty": True,
            "rule_state": {0: (1, False), 1: (1, True)},
        }
        policy = OfflineInactiveWindow(None, 1, True)
        with patch("scaling_eval.Sampling.generate", return_value=["neural"]) as gen:
            self.assertEqual(policy.generate(w, s, None, 4), [])
            gen.assert_not_called()
            self.assertEqual(
                policy.generate(w, dict(s, check_dirty=False), None, 4), ["neural"]
            )
            self.assertEqual(policy.generate(w, dict(s, menu=[1]), None, 4), ["neural"])
            self.assertEqual(
                policy.generate(w, dict(s, ports=[(None, None, None, 1)]), None, 4),
                ["neural"],
            )
