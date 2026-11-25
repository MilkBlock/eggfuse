import unittest

from scaling_bake import dependencies, graph_program, module, recursive_named


class ScalingBakeTest(unittest.TestCase):
    def test_all_tasks_are_ancestors_of_reported_endpoint(self):
        for n in (6, 16, 32, 64, 128, 256, 512):
            deps = dependencies("fork", n, 4)
            ancestors = {n - 1}
            for i in reversed(range(n)):
                if i in ancestors:
                    ancestors.update(deps[i])
            self.assertEqual(ancestors, set(range(-4, n)))

    def test_recursive_link_keeps_port_position_and_independent_same_typed_sources(self):
        # Slot 0 and slot 1 remain distinct even when both have the same type.
        unit = [
            (7, 0, [(-1, 0), (-1, 1)]),
            (2, 1, [(0, 4)]),
            (9, 2, [(0, 9), (-1, 1)]),
            (4, 4, [(1, 8), (2, 2)]),
        ]
        self.assertEqual(recursive_named(unit), unit)
        steps = [(7, [1, 2], {4: 3, 9: 4}), (2, [3], {8: 5}), (9, [4, 2], {2: 6}), (4, [5, 6], {1: 7})]
        self.assertEqual(module(steps), module(steps, True))

    def test_offset_changes_every_value_without_changing_wiring(self):
        _, a = graph_program("fork", 32, 4, 17, 8)
        _, b = graph_program("fork", 32, 4, 73, 8)
        self.assertEqual(set(a), set(b))
        self.assertTrue(all(b[k] - v == 56 for k, v in a.items()))
