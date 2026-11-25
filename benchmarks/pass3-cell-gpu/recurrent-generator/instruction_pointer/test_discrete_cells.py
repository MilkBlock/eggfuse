import unittest

from discrete_draft import Cell, Local, change, plan, script, valid


class DraftTest(unittest.TestCase):
    def test_named_dependencies_survive_insertion_and_block_dangling_or_wrong_port(self):
        root = Cell(1, ((8, 1, 2),))
        consumer = Cell(2, (Local(0, 3),))
        original = plan((root, consumer))
        checked = lambda source, port, user, slot: source.rule == 1 and port == 3
        new = change(original, 0, 0, Cell(3, ()), checked, fresh_uid=4)
        self.assertEqual([v.uid for v in new], [4, 0, 1])
        self.assertEqual(new[-1].cell.refs[0], Local(0, 3))
        self.assertEqual(change(new, 1, 1, compatible=checked), new)
        self.assertEqual(change(new, 1, 2, Cell(7, ()), checked), new)
        self.assertFalse(valid(tuple(reversed(original)), checked))
        self.assertTrue(valid(change(change(new, 2, 1), 1, 1), checked))
        self.assertEqual(original[0].cell, root)

    def test_bridge_deletes_consumers_before_replacing_producers(self):
        original = plan([Cell(0, ()), Cell(1, (Local(0, 0),)), Cell(2, (Local(1, 3),))])
        target = plan([Cell(0, (), True)])
        path = script(original, target)
        self.assertEqual([op for _, _, op, _ in path], [1, 1, 2])
        x = original
        for before, i, op, v in path:
            self.assertEqual(x, before)
            x = change(x, i, op, v)
            self.assertTrue(valid(x))
        self.assertEqual(x, target)

    def test_duplicate_is_a_real_edit(self):
        q = Cell(4, ((6, 0, 3),))
        before = plan([q, q])
        self.assertEqual(len(before), 2)
        self.assertEqual(script(before, plan([q])), [(before, 1, 1, None)])
        self.assertEqual(script(before, before), [])


if __name__ == "__main__":
    unittest.main()
