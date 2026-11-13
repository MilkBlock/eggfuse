import unittest
from subcell_patterns import signature, mine


class Patterns(unittest.TestCase):
    def test_alpha_equivalence(self):
        self.assertEqual(signature([(3, [8, 9]), (4, [9, 10])]),
                         signature([(3, [51, 0]), (4, [0, 9])]))

    def test_operator_and_alias_distinction(self):
        a = signature([(3, [1, 2]), (4, [2, 3])])
        self.assertNotEqual(a, signature([(3, [1, 2]), (5, [2, 3])]))
        self.assertNotEqual(a, signature([(3, [1, 2]), (4, [2, 1])]))
        self.assertNotEqual(a, signature([(3, [None, 2]), (4, [2, 3])]))

    def test_union_roots_do_not_create_static_edges(self):
        storage = dict(components=[dict(id=0, shape=0, frames=[1], frame_codes=[0], roots=[7,7,7,7])],
                       shapes=[dict(programs=[0], ports=[[0,1,2,3]])],
                       programs=[dict(fields=[[0,1],[2,3]])], operators=[[3,4]])
        facts = [dict(cell=1, template=0, started_epoch=0, facts=[
            dict(op=i, owned=True, hidden=False, born=0, epoch=0) for i in range(2)])]
        self.assertFalse(mine(storage, facts))
        storage['programs'][0]['fields'][1] = [1,3]
        self.assertEqual(len(mine(storage, facts)), 1)
        facts[0]['facts'][0]['hidden'] = True
        self.assertFalse(mine(storage, facts))
