import unittest
from types import SimpleNamespace

from compatibility_study import align
from compatibility_world import source


class PairTest(unittest.TestCase):
    def test_one_scalar_only(self):
        for sides in ("LR", "LRT"):

            def src(f, sides=sides):
                return source(3, sides, 4, True, 101, 44556, f).splitlines()

            changed = [
                (a, b) for a, b in zip(src(False), src(True), strict=True) if a != b
            ]
            self.assertEqual(len(changed), 1)
            a, b = changed[0]
            self.assertEqual(a.split()[:2], b.split()[:2])
            self.assertTrue(a.startswith("(Seed "))

    def test_unrelated_or_implicit_witness_changes_rejected(self):
        w = SimpleNamespace(tabs=["Seed", "Noise"], primitives=2)
        ref = (-1, 0, 0)

        def state(flip, noise, tail):
            def port(uid, tab, fields):
                return ((uid, 0, 0), uid, -1, tab, fields, False, ())

            return (
                {
                    "ports": [
                        port(-1, 0, (4, 7 if flip else 4, tail)),
                        port(-3, 1, (noise,)),
                    ],
                    "menu": [0, 2, 3],
                },
                [(3 if flip else 2, (ref,))],
            )

        left = state(False, 9, 12)
        self.assertEqual(align(left, state(True, 9, 12), w), (ref, [2, 3]))
        for changed in (state(True, 7, 12), state(True, 9, 17)):
            with self.assertRaises(AssertionError):
                align(left, changed, w)


if __name__ == "__main__":
    unittest.main()
