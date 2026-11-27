import unittest

from scaling_campaign import Campaign


class SelectionTests(unittest.TestCase):
    def test_replicated_rank_treats_each_program_equally(self):
        c = object.__new__(Campaign)
        groups = {}
        for seed in (71, 113):
            groups[f"balanced-s{seed}-t30000"] = {
                "inner_area": {"egg": 0.06, "one": 0.34, "two": 0.36}
            }
            groups[f"specialist-s{seed}-t30000"] = {
                "inner_area": {"egg": 0.04, "one": 0.32, "two": 0.91}
            }
        c.state = {"groups": groups}
        self.assertEqual(
            c.order(["specialist", "balanced"], 30000, [71]), ["specialist", "balanced"]
        )
        self.assertEqual(
            c.order(["specialist", "balanced"], 30000, [71, 113]),
            ["balanced", "specialist"],
        )

    def test_incomplete_seed_cannot_win(self):
        c = object.__new__(Campaign)
        c.state = {"groups": {"one-s71-t30000": {"inner_area": {"egg": 1.0}}}}
        self.assertEqual(c.order(["one"], 30000, [71, 113]), [])


if __name__ == "__main__":
    unittest.main()
